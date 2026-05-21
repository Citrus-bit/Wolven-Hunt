# Wolven Hunt 首期架构骨架修订计划 v3

## Summary

- 首版固定 8 人板：**3 狼人 + 2 村民 + 1 预言家 + 1 骑士 + 1 守卫**。
- 胜负条件：
  - **狼人胜**：`alive_wolves > alive_good_players`（严格大于），或 `alive_good_players == 0`（屠城）。
  - **好人胜**：`alive_wolves == 0`。
- 预言家规则：每晚查验一名玩家（**可查死人**，**不可查自己**），只返回阵营（`wolf` / `good`），不返回具体角色。
- 首夜可以死亡；**只有首夜被刀死亡的玩家**在首日白天有遗言，后续夜晚死亡玩家无遗言。
- 骑士可在白天投票开始前任意时间发动一次决斗；发动后跳过当日后续发言与投票。
- 投票只能投存活玩家，允许投自己；PK 重投只能投 PK 台上玩家，且 PK 台上玩家不参与重投。
- 编排核心采用**纯 Python FSM 优先**；裁判层（Referee）负责视角隔离与合法性校验；**事件日志是单一事实源**。
- 规则、角色、模型、提示词全部**配置驱动**，核心代码不随板子变化。
- 第一阶段目标：**只创建目录骨架和 architecture.md**，但 architecture.md 必须把规则契约、状态机子状态、事件 schema、异常 fallback、回放模式写死，避免后续返工。

---

## 1. 规则契约（Rule Contract）

### 1.1 配置组合

`GameConfig = RolePack + RuleSet + ModelRoster + PromptPack + random_seed`

- 新增板子时只改配置，不改核心代码。
- 每局 `game_start` 记录 `random_seed`、`config_hash`、座位号范围、角色分配结果；回放校验必须使用同一组 metadata。
- `config_hash` 作为 game metadata 进入所有 replay 校验，不要求每条事件重复存储。
- LLM 原始响应只进入私有存储；事件日志只记录 hash 与 storage ref。

### 1.2 首版 RolePack（classic_8）

- 狼人 × 3、村民 × 2、预言家 × 1、骑士 × 1、守卫 × 1。
- 座位统一使用 1-based 编号，首版固定为 1–8 号。
- `GAME_START` 使用 `random_seed` 派生的 deterministic RNG 洗牌分配角色到座位。
- 玩家只知道自己的角色；狼人额外知道全部狼队同伴身份。
- spectator 视角不暴露隐藏身份，只展示公开事件。

### 1.3 首版 WinCondition

- 每次「夜晚结算」「骑士挑战」「投票放逐」后**立即**执行胜负检查。
- 三条胜负规则按上述 Summary 写死，写入 `majority_or_massacre_all.yaml`。

### 1.4 预言家

- 每晚一次行动；目标可以是任意玩家，包括已死亡玩家。
- **不能查验自己**（首版默认；后续通过 RuleSet 开关扩展）。
- 结果只返回 `wolf` / `good` 阵营，不暴露具体角色。
- 生成 `seer_check_result` 私有事件，仅预言家本人可见。
- 预言家死亡后不再被调用，不能继续查验。
- 允许重复查验同一玩家，事件日志会记录。

### 1.5 守卫

- 首夜可守，可自守。
- **不可连续两晚守同一目标**（包括「首夜→第二夜」，包括自守）。
- 非法目标 → Referee 在 `validate_action` 阶段拒绝并要求 Agent 重选；重试上限耗尽走 fallback（见 §4）。
- 狼刀被守护时生成显式 `no_death_tonight` 事件（不暴露原因）。

### 1.6 狼人

- 每晚最多 1 轮夜聊（每狼一句），然后**同时**提交刀人目标。
- 多数决定刀人目标；平票时**在被狼队投到的目标中随机**选择，并记录 `wolf_tie_random` 事件。
- 合法刀人目标 = 所有存活非狼玩家。**不允许自刀、不允许刀狼队友、不允许空刀**。
- 狼队夜聊内容仅狼队可见。

### 1.7 骑士

- 白天**投票阶段开始前任意时间段**可发动一次，首日可发动。
- 骑士不能在夜晚发动，也不能在投票已经开始后插入发动。
- 挑战目标必须是当日存活玩家，不能是自己。
- 挑战结果：
  - 若目标是狼人 → **目标当场死亡**，生成 `knight_challenge`、`knight_result`、死亡事件与 `win_check`；目标无遗言。
  - 若目标是好人 → **骑士死亡**，被挑者继续存活，生成 `knight_challenge`、`knight_result`、死亡事件与 `win_check`；骑士有遗言。
- 骑士发动后跳过当日剩余发言与投票；若游戏未结束，直接进入当天夜晚。
- 骑士死亡后不能再发动；每局最多发动一次。

### 1.8 发言与投票

- 首夜可以死亡，`rule_set.first_night_can_die: true` 作为首版默认配置。
- 首夜死亡在首日 `DAY_ANNOUNCE` 公示；首夜被刀死亡者进入首日 `DAY_LAST_WORDS`。
- 白天按座位顺序一轮发言，每名存活玩家一次，中文默认 300 字上限。
- 投票：同时投票、公开票型、**不允许弃票、不允许改票、无警长**。
- 首轮投票合法目标 = 所有存活玩家，**允许投自己**，不能投已死亡玩家。
- 首轮平票 → 进入 `DAY_VOTE_PK`，平票玩家各一次 PK 发言后重投。
- PK 重投合法目标 = PK 台上的存活玩家；PK 台上的玩家不能参与重投。
- PK 重投如果第二次再次平票，则视为平安日，不放逐任何人，直接进入夜晚。
- 如果 PK 重投时除 PK 台上玩家外无人存活可投，则直接按二次平票/平安日处理并入夜。

### 1.9 遗言

- **有遗言**：白天被放逐者、骑士挑战错误死亡的骑士、首夜被刀死亡者。
- **无遗言**：第二夜及之后的夜晚死亡者、被骑士挑战死亡的狼人。

### 1.10 死亡 Agent 生命周期

- 死亡 Agent 停止被调用决策。
- 默认 PlayerView **冻结到死亡公示事件**之前的所有可见事件 + 死亡公示本身。
- 死亡后**仍接收全局公开事件**（后续公示、放逐结果、胜负结果），保证回放时死人也能理解游戏走向。
- 调试模式可让死亡 Agent 继续接收所有公开事件（用于评测）。

---

## 2. 夜晚行动顺序与状态机粒度

### 2.1 FSM 子状态（显式拆细，与事件日志一一对应）

```
GAME_START
  → NIGHT_START
    → NIGHT_GUARD          # 守卫行动
    → NIGHT_WOLF_CHAT      # 狼队夜聊（1 轮）
    → NIGHT_WOLF_VOTE      # 狼队同时投刀
    → NIGHT_SEER           # 预言家查验
    → NIGHT_RESOLVE        # 结算：守 vs 刀，生成死亡/no_death_tonight 事件
    → CHECK_WIN
  → DAY_ANNOUNCE           # 公示夜晚结果
    → DAY_LAST_WORDS?      # 仅首夜被刀死亡者有遗言；其他夜死跳过
    → DAY_SPEECH           # 按座位顺序发言
    → DAY_KNIGHT_INTERRUPT?# DAY_ANNOUNCE 后至 DAY_VOTE 前均可触发
    → DAY_VOTE             # 同时投票
    → DAY_VOTE_PK?         # 平票时进入；PK 台下玩家重投
    → DAY_EXILE?           # 有放逐才进入；二次平票平安日则跳过
    → CHECK_WIN
  → 循环回 NIGHT_START
GAME_END
```

### 2.2 结算顺序（NIGHT_RESOLVE）

1. 读取本晚 `guard_protect` 目标 G、`wolf_kill` 目标 K、`seer_check` 目标 S。
2. 若 G == K → 生成 `no_death_tonight` 事件；否则 K 死亡，生成 `death_at_night` 事件。
3. 首夜死亡会在首日 `DAY_ANNOUNCE` 公示，并触发 `DAY_LAST_WORDS`；第二夜及之后夜死无遗言。
4. `seer_check_result` 在 `NIGHT_SEER` 时已生成，结算阶段不再处理。
5. 死亡事件不暴露死因（不区分「被刀」「被救」）。

### 2.3 同夜信息可见性

- 狼人**不知道**今晚是否被守（只知道自己投了谁）。
- 预言家查验结果在 `NIGHT_SEER` 状态结束时立即对预言家可见（私有事件）。
- 守卫**不知道**自己是否守住了刀（避免反向推理狼队目标）。

### 2.4 首日规则（默认值）

- 首夜：守卫/狼人/预言家**正常行动**。
- 首夜可以死亡（即 `first_night_can_die: true`）。
- 首日白天：公示首夜死亡结果；如果首夜有人被刀死亡，执行 `DAY_LAST_WORDS`，否则跳过遗言直接进入 `DAY_SPEECH`。
- 首日发言起点座位号通过 `rule_set.first_speaker_seat` 配置（默认 1 号）。

### 2.5 骑士中断规则

- 骑士窗口不是固定线性子状态，而是 `DAY_ANNOUNCE` 结束后到 `DAY_VOTE` 开始前的可中断动作。
- 若骑士在任意白天投票前节点发动，FSM 立即暂停当前白天流程，结算骑士决斗与胜负。
- 若胜负未产生，跳过当日剩余发言和投票，直接进入 `NIGHT_START`。
- 若骑士未发动，白天流程按 `DAY_SPEECH → DAY_VOTE → DAY_VOTE_PK? → DAY_EXILE` 推进。

---

## 3. 事件日志（Event Log）

### 3.1 设计原则

- **事件日志是单一事实源**：所有 PlayerView、回放、胜负判定都从事件日志派生。
- 事件**不可变**，append-only。
- 每个事件携带 `schema_version`，未来 schema 演化时保证向后兼容。
- 每局私有 metadata 包含 `random_seed`、`config_hash`、`seat_range`、`role_assignment`；这些字段由存储层的 `game_start` 记录，并用于 replay 校验。
- PlayerView 中的 `game_start` 必须经过 Referee 脱敏：本人只看到自己的角色，狼人额外看到狼队同伴，spectator 不看到隐藏身份。
- 所有随机决策必须使用 `random_seed` 派生的 deterministic RNG stream；随机事件 payload 记录候选集、选中值、原因。

### 3.2 事件字段（公共）

```
{
  "event_id": uuid,
  "schema_version": "1.0",
  "game_id": uuid,
  "seq": int,                 # 全局单调递增
  "phase": str,               # FSM 子状态
  "day": int,
  "timestamp": iso8601,
  "type": str,                # 见 3.3 枚举
  "actor": int | null,        # 玩家 seat
  "visibility": {             # 可见性：白名单 seat 或 "public"/"wolves"
    "public": bool,
    "seats": [int]
  },
  "payload": {...}            # PlayerView 前必须按 visibility/role 脱敏
}
```

### 3.3 事件类型枚举（v1.0）

- 流程：`game_start`, `phase_enter`, `phase_exit`, `game_end`
- 夜晚：`guard_protect`, `wolf_chat_message`, `wolf_kill_vote`, `wolf_kill_decided`, `wolf_tie_random`, `seer_check`, `seer_check_result`, `no_death_tonight`, `death_at_night`
- 白天：`day_announce`, `last_words`, `speech`, `knight_challenge`, `knight_result`, `vote_cast`, `vote_result`, `vote_pk_enter`, `peaceful_day`, `exile`
- 系统：`win_check`, `agent_timeout`, `agent_invalid_action`, `agent_fallback_triggered`
- 元数据：`llm_call`（包含 `prompt_hash`、`raw_response_hash`、`storage_ref`、model、token、cost，**仅写入存储层，不进 PlayerView**）
- 随机：涉及平票随机、fallback 随机、角色洗牌的事件 payload 均记录 `rng_stream`、`candidates`、`selected`、`reason`。

### 3.4 可见性规则

- 公共事件（`public: true`）：所有玩家可见（含死亡 Agent，见 §1.10）。
- 狼队事件（`wolf_chat_message`, `wolf_kill_vote`, `wolf_kill_decided`）：仅狼队 seat 可见。
- 私有事件（`seer_check_result`, `guard_protect`）：仅 actor 可见。
- `llm_call`、完整 `role_assignment`、raw response 存储引用默认不进入任何 PlayerView；只有存储层和调试工具可读。
- **Referee 是唯一权限边界**，PlayerView 由 Referee 按 visibility 过滤生成。

---

## 4. LLM 异常与 Fallback（写入 RuleSet）

### 4.1 三类异常

1. **超时**：单次调用 > `llm.timeout_seconds`。
2. **非法 JSON / schema 校验失败**：Pydantic 解析失败。
3. **合法性校验失败**：通过 schema 但违反规则（如刀狼队友、连守同一人）。

### 4.2 重试策略

- 每阶段每 Agent 最多重试 `llm.max_retries` 次（默认 2 次，可配置）。
- 重试时在 prompt 末尾附加错误说明（仅本人可见）。
- 重试仍失败 → 触发 fallback 并记录 `agent_fallback_triggered` 事件。

### 4.3 各阶段 Fallback 行为（默认）

| 阶段 | Fallback |
|---|---|
| `NIGHT_GUARD` | 随机选一个合法目标（排除昨晚守护对象） |
| `NIGHT_WOLF_CHAT` | 发送空消息（占位 `[沉默]`） |
| `NIGHT_WOLF_VOTE` | 随机选一个合法目标 |
| `NIGHT_SEER` | 随机选一个非自己玩家 |
| `DAY_SPEECH` | 默认模板「我没有更多信息」 |
| `DAY_KNIGHT_INTERRUPT` | 默认不发动 |
| `DAY_VOTE` | 随机选一个存活玩家（允许自己） |
| `DAY_VOTE_PK` | 台下玩家随机投一个 PK 台上存活玩家；如无台下玩家可投，直接平安日 |
| `DAY_LAST_WORDS` | 默认模板「我没有遗言」 |

- 所有 fallback 行为均**写入 RuleSet**，黄金测试必须覆盖。
- 所有 fallback 随机均使用 deterministic RNG，并在对应事件 payload 中记录候选集、选中值与 fallback 原因。

---

## 5. 回放与可复现性

### 5.1 两种 Replay 模式

- **`replay_deterministic`**：从事件日志直接渲染时间线，不调用 LLM。用于 UI 复盘、教学、争议复核。
- **`replay_resimulate`**：使用存储的 `llm_call` 原始响应重跑 FSM，断言事件序列与原日志一致。用于回归测试、引擎重构后的等价性验证。

### 5.2 必须记录的字段

- 存储层 `game_start` 记录 `random_seed`、`config_hash`、`seat_range`、`role_assignment`；进入 PlayerView 前必须脱敏。
- 每个 LLM 调用的公开索引字段：model、prompt hash（不存原文，存哈希 + prompt_version 引用）、raw response hash、storage ref、token usage、cost。
- 完整 raw response 仅写入私有存储，用于 `replay_resimulate`；`llm_call` 事件不直接包含原文，不进 PlayerView。
- 所有随机决策必须可由 `random_seed + rng_stream + candidates` 重建；事件记录 selected 结果用于一致性断言。

### 5.3 Prompt 模板版本号

- `configs/prompts/zh/seer/night_action.v3.md`，文件名带版本号。
- 事件日志记录 `prompt_version`，修改 prompt 后老日志仍可解释。

---

## 6. Prompt 注入与越权防御

### 6.1 输入侧（PlayerView）

- **Referee 不审查 Agent 发言内容**，只保证注入到 prompt 的私有信息正确脱敏。
- Agent 在发言里声称「我查了 3 号是狼」属于**合法角色扮演**，由游戏机制处理（信任/怀疑）。
- 泄漏测试覆盖：预言家结果、狼队身份、守卫目标不出现在非授权玩家的 PlayerView 中。

### 6.2 输出侧

- 所有 LLM 输出必须走 Pydantic / JSON Schema 校验。
- Schema 校验失败 → 走 §4 fallback。

### 6.3 PlayerView 大小控制

- 使用**最近事件窗口 + 确定性历史摘要**，避免 prompt 无限增长。
- 摘要算法纯函数（基于事件日志），保证可复现。
- 每局 token 上限通过 `llm.budget_per_game` 配置，超限触发告警（不强制中止）。

---

## 7. 目录结构

```
.
├── architecture.md                          # 主架构文档（本文档落地后扩写）
├── plan.md                                  # 本计划
├── configs/
│   ├── games/
│   │   ├── classic_8.yaml                   # 首版 8 人局完整配置
│   │   ├── _role_packs/
│   │   │   └── classic_8_three_gods.yaml
│   │   └── _rule_sets/
│   │       └── majority_or_massacre_all.yaml
│   ├── models/
│   │   ├── providers.yaml
│   │   └── roster.yaml
│   └── prompts/
│       ├── zh/{seer,guard,wolf,knight,villager}/{night_action,speech,vote,last_words}.v1.md
│       └── en/...
├── docs/
│   └── specs/                               # 阶段交付规格（GPT 执行手册 + 验收指标）
│       └── STEP-01-lobby-home.md
├── .env.example
├── package.json                             # 前端入口壳（Vite + React + TS），见 §14
├── package-lock.json                        # npm 依赖锁文件
├── index.html                               # 前端入口 HTML
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── public/
│   └── assets/lobby/                        # 大厅静态资源（ASCII 命名）
│       ├── lobby_pingpong.mp4               # 由 scripts/build-lobby-pingpong.mjs 生成；产物随仓库提交
│       ├── lobby_bgm.mp3
│       ├── lobby_poster.jpg
│       ├── btn_start.png
│       ├── btn_history.png
│       └── btn_settings.png
├── 素材/                                    # 中文原始素材，仅作为构建输入，不参与运行时
├── scripts/
│   └── build-lobby-pingpong.mjs             # 跨平台 Node 脚本（依赖 ffmpeg-static），生成 ping-pong mp4
├── src/wolven_hunt/                         # Python 引擎
│   ├── core/                                # GameState, Event, Role, RuleEngine, WinCondition
│   ├── referee/                             # PlayerView, validate_action, visibility filter
│   ├── orchestration/                       # FSM；后续 LangGraph adapter 边界
│   ├── agents/                              # PlayerInterface, LLMPlayer, HumanPlayer stub
│   ├── llm/                                 # LiteLLM 网关、structured output、重试、fallback、成本记录
│   ├── storage/                             # 事件日志、快照、回放（两种模式）
│   └── api/                                 # FastAPI 控制接口
├── src/                                     # 前端入口壳（与 wolven_hunt/ 互不导入），见 §14
│   ├── main.tsx
│   ├── App.tsx
│   ├── styles.css
│   ├── components/
│   │   └── Lobby/
│   │       ├── LobbyHome.tsx
│   │       ├── LobbyVideo.tsx
│   │       ├── LobbyButtons.tsx
│   │       └── MuteToggle.tsx
│   └── hooks/
│       └── useLobbyAudio.ts
└── tests/
    ├── unit/                                # RuleEngine 纯函数单测
    ├── integration/                         # FSM 全流程
    ├── leakage/                             # PlayerView 脱敏
    ├── golden/                              # 固定 seed + mock Agent 黄金回放
    └── property/                            # hypothesis 不变量
```

---

## 8. 架构决策

- `RuleEngine.apply(state, action) -> (new_state, events)` 是纯函数，不接受 `player_id`，不读取 PlayerView。
- Referee 是唯一权限边界：生成脱敏视角、校验行动、分发事件可见性。
- Agent 调用链固定：
  `FSM → Referee.build_view → PlayerInterface.decide → Pydantic 校验 → Referee.validate_action → RuleEngine.apply → EventLog.append`
- FSM 子状态显式拆细（§2.1），与事件日志一一对应。
- 所有 LLM 输出必须走 Pydantic / JSON Schema；失败 → 重试 → fallback。

---

## 9. 模型与 API

### 9.1 LLM 网关

- LiteLLM 统一调用多厂商模型；`base_url` 和 `api_key` 通过环境变量注入。
- `.env` 进 `.gitignore`，CI 使用 mock provider。
- `roster.yaml` 将 8 个座位绑定到模型 profile，支持 personality tag。
- 成本记录**落盘**（per-game token usage + cost），方便后期对账。

### 9.2 FastAPI 接口（P2，不属于第一阶段）

- 第一阶段不实现 FastAPI、SSE、真实 LLM 网关、Replay 运行时代码；这些接口只在 `architecture.md` 中定义边界，避免目录骨架阶段范围膨胀。

- `POST /games`：创建一局
- `GET /games/{id}`：当前状态（脱敏到 spectator 视角）
- `GET /games/{id}/events`：事件日志（spectator 视角）
- `POST /games/{id}/run` / `pause` / `resume`：流程控制
- `POST /games/{id}/replay`：触发 replay（参数：`mode=deterministic|resimulate`）
- `POST /games/{id}/dev/inject`：dev-only，注入动作
- `GET /games/{id}/stream`：SSE 流式推送事件

---

## 10. 测试计划

### 10.1 规则黄金测试（unit + golden）

- 预言家：查活人、查死人、重复查验、死亡后不调用、结果只返回阵营、不能查自己。
- 胜负：狼严格人数优势胜、屠城胜、好人全灭狼胜、狼全灭好人胜、每个检查点都触发。
- 流程：首夜死亡并触发遗言、第二夜及以后夜死无遗言、首夜守卫平安夜、平票 PK、二次平票平安日、骑士挑战狼/挑错好人、遗言规则、首日规则。
- 死亡 Agent 停用 + 仍接收公开事件。

### 10.2 泄漏测试（leakage）

- 预言家结果仅本人 PlayerView 可见。
- 狼队身份/夜聊/投刀仅狼队可见。
- 守卫目标仅守卫本人可见。
- 所有死亡事件不暴露死因。

### 10.3 异常路径测试

- LLM 超时、非法 JSON、违规动作 → 重试 → fallback。
- 每阶段 fallback 行为符合 §4.3 表格。
- fallback 随机行为在固定 seed 下完全可复现。

### 10.4 流程测试（integration）

- mock 8 个 deterministic Agent 跑 100 局，断言：
  - 无异常退出；
  - 胜负必收敛（不存在死循环）；
  - 事件日志可被 `replay_deterministic` 完整重放；
  - 事件日志可被 `replay_resimulate` 重跑且结果一致。
- 骑士可在 `DAY_ANNOUNCE` 后、任意玩家发言后、`DAY_VOTE` 前发动；发动后跳过当日剩余白天流程。
- 投票可投自己但不能投死人；PK 重投只能投 PK 台上存活玩家，PK 台上玩家不参与重投。

### 10.5 Property-based 测试（hypothesis）

- 不变量：
  - 存活玩家数单调递减；
  - `alive_wolves + alive_good == alive_total`；
  - 任意时刻事件日志 seq 严格递增；
  - PlayerView 不包含 visibility 白名单外的事件。

### 10.6 公平性回归

- 固定模型组合跑 100+ 局，记录好人/狼人胜率。
- 设定合理区间（如狼人胜率 40%~70%），超出告警。
- 用于评估 prompt 改动、模型升级是否破坏平衡。

### 10.7 成本预算测试

- 单局 token 使用上限断言（默认 100k tokens/局，可配置）。
- 超限触发测试失败，防止 prompt 失控膨胀。

### 10.8 LLM 网关测试

- mock LiteLLM，验证多 provider、structured output、重试、fallback、成本记录。

---

## 11. 实施优先级

| 优先级 | 任务 | 说明 |
|---|---|---|
| P0 | 写完 `architecture.md` 并冻结：FSM 子状态、事件枚举、夜晚结算顺序、LLM fallback 表 | 规则骨架，缺了无法写代码 |
| P0 | 目录骨架 + 配置模板（classic_8.yaml + rule_set + role_pack） | 第一阶段交付物 |
| P0 | `.env.example` + `.gitignore` | 安全前置 |
| P0 | 前端入口壳（大厅 Home）+ 资源构建脚本 | 单独交付物，不阻塞 Python 引擎进度；契约见 §14 |
| P1 | RuleEngine 纯函数 + 事件 schema 实现 | 核心 |
| P1 | Referee + PlayerView + 泄漏测试 | 权限边界 |
| P1 | FSM 编排 + mock Agent + 100 局集成测试 | 跑通闭环 |
| P2 | LLM 网关（LiteLLM + 重试 + fallback + 成本记录） | 接入真模型 |
| P2 | Replay 两种模式 + Prompt 版本号 | 长期可维护 |
| P2 | FastAPI + SSE | 外部接入；第一阶段只在 architecture.md 定义接口边界 |
| P3 | Property test、公平性回归、Token 预算测试 | 工程化体验 |

---

## 12. 假设与待确认项

1. **预言家可查死人**为首版明确规则，不视为调试特权。
2. **不能查验自己**作为默认规则，后续可通过 RuleSet 开关扩展。
3. **狼人人数 > 好人人数**按严格大于 `>` 实现。
4. **首夜可以死亡**作为默认，`first_night_can_die: true`。
5. **首夜被刀死亡者有遗言**是唯一夜死遗言例外；第二夜及以后夜死无遗言。
6. **骑士投票前任意时间发动**仅限白天，投票开始后不能插入。
7. **投票允许投自己**，但不能投死亡玩家。
8. **PK 重投只投 PK 台上玩家**，PK 台上玩家不参与重投；二次平票平安日入夜。
9. **死亡 Agent 仍接收公开事件**，便于回放完整性。
10. **Referee 不审查发言内容**：发言里的虚假信息属合法策略。
11. **第一阶段只创建目录骨架和 architecture.md**，不实现业务逻辑；但 architecture.md 内容必须把 §1–§6 全部写死。

## 13. 项目系统提示词与变更纪律

- 仓库根目录 `AGENTS.md` 是本项目的开发代理系统提示词。
- 此后任何代码变更、配置变更、prompt 变更、测试变更或架构契约变更，都必须先检查本 `plan.md`。
- 如果实际实现需要改变本计划中的规则、目录、接口、FSM 子状态、事件 schema、fallback、replay 或测试约定，必须先更新 `plan.md`，再修改代码或配置。
- 如果变更只是落实现有计划，也要确保新增文件、模块命名和行为边界与本 `plan.md` 保持一致。
- `architecture.md` 是本计划第一阶段的架构契约落地文档。后续实现不得绕过其中定义的 Referee 权限边界、事件日志单一事实源、配置驱动规则、纯 Python FSM 优先、可复现 replay 和 LLM fallback 约束。

以上假设若有不同意见，请在进入实施前明确。

## 14. 前端入口骨架（Web Lobby Shell）

第一阶段除了 Python 引擎骨架外，前端只交付一个**大厅 Home 壳**，用于承接素材并作为后续接入 FastAPI 的可见入口。本节冻结前端壳的契约，使其与 §1–§6 的规则契约**互不影响、互不导入**。

### 14.1 模块边界

- 前端代码统一放在仓库根目录：`package.json`、`package-lock.json`、`index.html`、`vite.config.ts`、`tsconfig.json`、`tsconfig.node.json`、`src/components/`、`src/hooks/`、`src/main.tsx`、`src/App.tsx`、`src/styles.css`、`public/`。
- 与 `src/wolven_hunt/` Python 引擎在同一仓库下共存，但**双向不导入**：前端不通过任何方式引用 `src/wolven_hunt/*` 或 `configs/*`；Python 引擎也不依赖前端。
- 前端只消费 **spectator 脱敏视角**。任何玩家视角、行动校验、私有信息均通过后续 P2 FastAPI（§9.2）暴露，**不得绕过 Referee**。
- 第一阶段大厅页**没有任何后端调用**：纯静态资源 + UI 状态，不发起 HTTP / WebSocket / SSE 请求。

### 14.2 前端栈

- Vite + React 18 + TypeScript（与既有 `dist/` 产物一致）。
- 使用 npm 管理依赖，`package-lock.json` 必须随 `package.json` 提交以保证安装可复现。
- 图标使用 `lucide-react`。
- 不引入额外的 CSS 框架；样式集中在 `src/styles.css` 与组件局部 className。
- 不引入路由库；按钮 click 仅 stub（`console.log` + 可选回调），等待后续步骤接入二级页。

### 14.3 静态资源命名规范

- 运行时资源放在 `public/assets/lobby/`，文件名一律 **ASCII 小写蛇形**，例如：
  - `lobby_pingpong.mp4`
  - `lobby_bgm.mp3`
  - `lobby_poster.jpg`
  - `btn_start.png`
  - `btn_history.png`
  - `btn_settings.png`
- 中文素材保留在 `素材/` 目录，仅作为构建输入，不被运行时直接引用。

### 14.4 大厅动图（ping-pong）

- 大厅首页以「大厅界面_动图」为主视觉，要求**正放→倒放→正放**无缝循环。
- 实现方式固定为「**预生成 ping-pong MP4**」：构建期由跨平台 Node 脚本 `scripts/build-lobby-pingpong.mjs` 调用 npm devDependency `ffmpeg-static` 提供的 ffmpeg 二进制，把原片正放 + 倒放拼接为单段 mp4；运行时只用 `<video autoplay muted loop playsInline>`。
- 脚本不依赖系统 ffmpeg，也不依赖 bash；`ffmpeg-static` 已覆盖 Linux / macOS / Windows × x64 / arm64。贡献者只需 `npm install && npm run assets:lobby` 即可重新生成 ping-pong mp4。
- 不允许使用 `playbackRate=-1`、`currentTime` 反向 seek 或运行时双 video 切换等替代方案（避免跨浏览器抖动与移动端发热）。
- 视频源固定为 `素材/大厅界面_动图.mp4`，构建产物固定为 `public/assets/lobby/lobby_pingpong.mp4`。
- 海报兜底：`public/assets/lobby/lobby_poster.jpg`，源自 `素材/大厅界面.jpg`。

### 14.5 BGM 自动播放策略

- BGM 源固定为 `public/assets/lobby/lobby_bgm.mp3`（`素材/游戏大厅待机音乐.mp3`）。
- 进入大厅时音频元素 `muted=true` 自动播放（满足浏览器 autoplay policy）。
- **首次**用户交互（`pointerdown` 或 `keydown`）后立即解除静音并继续播放；解锁失败时（被浏览器拒绝）保持静音并 `console.warn`，不抛错。
- 用户可通过右上角浮动按钮在「有声 / 静音」之间切换。
- 不允许在未解锁前发声，不允许把 BGM 状态写入 `localStorage` 之外的任何来源（防止绕过 §3.1 单一事实源约束）。

### 14.6 大厅按钮

- 大厅下方水平显示三个按钮，从左到右顺序固定为：**开始游戏 → 历史复盘 → 系统设置**。
- 三张图标固定取自 `public/assets/lobby/btn_start.png` / `btn_history.png` / `btn_settings.png`。
- 第一阶段每个按钮 click 仅 stub：`console.log('[lobby] click: start' | 'history' | 'settings')`，并暴露可选回调 `onAction(kind)` 供后续步骤接入路由。
- `<button>` 必须可键盘聚焦，`aria-label` 与 `<img alt>` 使用中文按钮名。

### 14.7 行为禁区

第一阶段大厅页代码**不允许**包含以下内容：

- 任何 LLM 调用、随机数、规则判定、角色分配、投票、FSM 关键字。
- 直接读取 `src/wolven_hunt/*`、`configs/*`、事件日志或 game state。
- HTTP / WebSocket / SSE / Worker 请求。
- 写入 `localStorage` 以外的持久化存储。

### 14.8 资源构建脚本

- `scripts/build-lobby-pingpong.mjs` 是跨平台 Node 脚本，通过 npm devDependency `ffmpeg-static` 提供的 ffmpeg 生成 ping-pong mp4，可重入；输入与输出路径默认值固定如 §14.4。
- 第一阶段的 ping-pong 产物 `public/assets/lobby/lobby_pingpong.mp4` 随仓库提交，确保 `git clone && npm install && npm run dev` 即可看到大厅动图；脚本仅在替换素材时重跑。
- 替换素材时以「重跑脚本」为唯一可复现路径，不允许把生成产物当作不可重建素材纳入仓库假设。

### 14.9 阶段交付规格目录

- 每个阶段的执行规格放在 `docs/specs/STEP-{NN}-{slug}.md`，由本仓库代理（Kiro）写入，作为 GPT 实施手册与验收指标的镜像。
- 第一阶段对应 `docs/specs/STEP-01-lobby-home.md`。
