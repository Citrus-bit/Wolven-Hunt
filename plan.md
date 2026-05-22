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
- 当前阶段：**STEP-06 / P2 外部接入实现**。在 STEP-05 引擎基础上允许实现 LLM 网关、结构化输出校验、mock provider、LLMAgent、落盘 EventLog sink、`replay_resimulate`、FastAPI/SSE、CLI serve/resimulate 与前端 spectator 事件流接入。

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
- 系统：`win_check`, `agent_timeout`, `agent_invalid_action`, `agent_fallback_triggered`, `agent_budget_warning`
- 元数据：`llm_call`（包含 `prompt_hash`、`raw_response_hash`、`storage_ref`、model、token、cost，**仅写入存储层，不进 PlayerView**）
- `llm_call` payload 字段固定为：`prompt_hash: str`、`raw_response_hash: str`、`storage_ref: str`、`model: str`、`prompt_tokens: int`、`completion_tokens: int`、`cost_usd: float`、`prompt_version: str`。payload 不得包含 `raw_response` 原文。
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

错误子类映射：

| 子类 | 外显事件 |
|---|---|
| `timeout` / `rate_limit` / `network` | `agent_timeout` |
| `invalid_json` / `schema_violation` / `illegal_action` | `agent_invalid_action` |

### 4.2 重试策略

- 每阶段每 Agent 最多重试 `llm.max_retries` 次（默认 2 次，可配置）。
- 重试时在 prompt 末尾附加错误说明（仅本人可见），格式固定为：`上一次输出未被接受：{error_type}: {message}。请只返回符合 schema 的 JSON。`
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
- `replay_resimulate` 一致性比对维度固定为 `type, actor, day, phase, canonical_payload`；不要求 `event_id` 与 `timestamp` 字节相等。首个分歧必须报告 `(seq, field, expected, actual)`。

### 5.4 STEP-06 落盘目录

每局默认落盘到 `runs/{game_id}/`：

```
events.jsonl
raw_responses.jsonl
manifest.json
cost.jsonl
```

`events.jsonl` 与 EventLog 一一对应；`raw_responses.jsonl` 每行记录 `{storage_ref, seat, phase, day, seq, model, prompt_hash, raw_response_hash, raw_response, prompt_tokens, completion_tokens, cost_usd}`。所有文件权限为 `0600`。JSON/JSONL 写入必须采用 tmp + fsync + atomic rename 或行级 fsync；恢复时若末行损坏，截断到最后一条可解析完整 JSONL。

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

输出 JSON schema 按 phase 固定为：

| phase | 字段 |
|---|---|
| `NIGHT_GUARD` | `{target: int}` |
| `NIGHT_WOLF_CHAT` | `{text: str}` |
| `NIGHT_WOLF_VOTE` | `{target: int}` |
| `NIGHT_SEER` | `{target: int}` |
| `DAY_SPEECH` | `{text: str}` |
| `DAY_KNIGHT_INTERRUPT` | `{activate: bool, target: int | null}` |
| `DAY_VOTE` | `{target: int}` |
| `DAY_VOTE_PK` | `{target: int}` |
| `DAY_LAST_WORDS` | `{text: str}` |

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
│       ├── STEP-01-lobby-home.md
│       ├── STEP-02-lobby-modal-and-settings.md
│       └── STEP-03-game-preparation-page.md
├── .env.example
├── package.json                             # 前端入口壳（Vite + React + TS），见 §14
├── package-lock.json                        # npm 依赖锁文件
├── index.html                               # 前端入口 HTML
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── public/
│   └── assets/
│       ├── lobby/                              # 大厅静态资源（ASCII 命名）
│       │   ├── lobby_pingpong.mp4              # 由 scripts/build-lobby-pingpong.mjs 生成；产物随仓库提交
│       │   ├── lobby_bgm.mp3
│       │   ├── lobby_poster.jpg
│       │   ├── btn_start.png
│       │   ├── btn_history.png
│       │   ├── btn_settings.png
│       │   ├── settings_panel_bg.png           # 大厅弹窗背景框（见 §14.10）
│       │   ├── model_icon_minimax_laoshi.png   # 系统设置 8 个模型图标（见 §14.11）
│       │   ├── model_icon_wanwen.png
│       │   ├── model_icon_guangzhimingmian.png
│       │   ├── model_icon_dami.png
│       │   ├── model_icon_xueba.png
│       │   ├── model_icon_xiaodoubao.png
│       │   ├── model_icon_haiseyin.png
│       │   └── model_icon_ayuan_tishenban.png
│       └── game/                               # 游戏页静态资源（见 §14.13）
│           ├── day_bg.png                      # 白天背景
│           └── night_bg.png                    # 夜晚背景预备
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
│   ├── lib/
│   │   └── modelConfigs.ts                  # 8 个模型 slot 静态配置（见 §14.11）
│   ├── components/
│   │   ├── Lobby/
│   │   │   ├── LobbyHome.tsx
│   │   │   ├── LobbyVideo.tsx
│   │   │   ├── LobbyButtons.tsx
│   │   │   ├── MuteToggle.tsx
│   │   │   ├── LobbyModal.tsx               # 通用弹窗外壳（见 §14.10）
│   │   │   └── modals/
│   │   │       ├── StartModal.tsx
│   │   │       ├── HistoryModal.tsx
│   │   │       ├── SettingsModal.tsx
│   │   │       ├── VolumeSlider.tsx
│   │   │       └── ModelConfigList.tsx
│   │   └── Game/                            # 游戏准备页（见 §14.13）
│   │       ├── GamePage.tsx
│   │       ├── GameSeat.tsx
│   │       └── ModelPicker.tsx
│   └── hooks/
│       ├── useLobbyAudio.ts                 # 含 muted + volume + ensureUnlock
│       └── useLocalStorage.ts               # 通用受控 localStorage hook
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
- 超过单局预算时发出一次 `agent_budget_warning` 系统事件；游戏继续运行，不因预算告警中止。

#### 环境变量

STEP-06 引入以下环境变量（通过 `pydantic-settings.BaseSettings` 读入，封装在 `src/wolven_hunt/config/settings.py`）：

- `WH_LLM_PROVIDER`：`mock` | `litellm`，缺省为 `mock`；非法值启动失败
- `WH_LLM_API_KEY`：真实 provider 的 API key；`WH_LLM_PROVIDER=litellm` 时必填
- `WH_LLM_BASE_URL`：LiteLLM base URL，可选
- `WH_LLM_MODEL`：默认模型名，可选（roster.yaml 可覆盖）
- `WH_LLM_TIMEOUT_SECONDS`：单次调用超时，默认 30
- `WH_LLM_MAX_RETRIES`：重试预算，默认 2
- `WH_LLM_BUDGET_PER_GAME`：单局 token 上限，默认 100000
- `WH_RUNS_DIR`：落盘根目录，默认 `./runs`
- `WH_API_HOST`：FastAPI 监听地址，默认 `127.0.0.1`
- `WH_API_PORT`：FastAPI 监听端口，默认 8000
- `WH_API_CORS_ORIGINS`：CORS 白名单，逗号分隔，默认 `http://localhost:5173`

`.env` 已在 `.gitignore`；`.env.example` 列出全部变量（不含真值）。CI 使用 `WH_LLM_PROVIDER=mock`，不消耗 API key。

### 9.2 FastAPI 接口（STEP-06 实现）

- `POST /games`：创建一局
- `GET /games/{id}`：当前状态（脱敏到 spectator 视角）
- `GET /games/{id}/events`：事件日志（spectator 视角）
- `POST /games/{id}/run` / `pause` / `resume`：流程控制
- `POST /games/{id}/replay`：触发 replay（参数：`mode=deterministic|resimulate`）
- `POST /games/{id}/dev/inject`：dev-only，注入动作
- `GET /games/{id}/stream`：SSE 流式推送事件
- `POST /games/{id}/speech`：提交公开发言文本，仍走 Referee `validate_action`
- `POST /games/{id}/wolf_chat`：提交狼聊文本，仍走 Referee `validate_action`
- 错误体统一为 `{code: str, message: str, details?: object}`；4xx 表示业务/规则拒绝，5xx 表示系统错误。

SSE 线协议固定为：

```
event: game_event
id: <seq>
data: <spectator Event JSON>
```

每 30s 发送 `event: heartbeat\ndata: {}`。客户端携带 `Last-Event-ID: <seq>` 时，服务端从 `seq + 1` 续推；请求的 seq 不存在时返回 410。CORS 默认白名单为 `http://localhost:5173`，可通过 `WH_API_CORS_ORIGINS` 配置。

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
- CI 一律使用 mock provider；真实模型 smoke 只在显式环境变量开启时运行，不进入默认 `pytest`。

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
11. **STEP-06 / P2 阶段开始实现外部接入**：LLM 网关、FastAPI/SSE、默认 `runs/{game_id}` 落盘、`replay_resimulate` 与前端 spectator 事件流接入可以落地；CI 默认仍使用 mock provider。

## 13. 项目系统提示词与变更纪律

- 仓库根目录 `AGENTS.md` 是本项目的开发代理系统提示词。
- 此后任何代码变更、配置变更、prompt 变更、测试变更或架构契约变更，都必须先检查本 `plan.md`。
- 如果实际实现需要改变本计划中的规则、目录、接口、FSM 子状态、事件 schema、fallback、replay 或测试约定，必须先更新 `plan.md`，再修改代码或配置。
- 如果变更只是落实现有计划，也要确保新增文件、模块命名和行为边界与本 `plan.md` 保持一致。
- `architecture.md` 是本计划的架构契约落地文档。后续实现不得绕过其中定义的 Referee 权限边界、事件日志单一事实源、配置驱动规则、纯 Python FSM 优先、可复现 replay 和 LLM fallback 约束。

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
  - `settings_panel_bg.png`（弹窗背景框，源自 `素材/大厅设置栏.png`）
  - `model_icon_minimax_laoshi.png`（源自 `素材/minimax老师.png`）
  - `model_icon_wanwen.png`（源自 `素材/万问.png`）
  - `model_icon_guangzhimingmian.png`（源自 `素材/光之明面.png`）
  - `model_icon_dami.png`（源自 `素材/大米.png`）
  - `model_icon_xueba.png`（源自 `素材/学霸.png`）
  - `model_icon_xiaodoubao.png`（源自 `素材/小豆包儿.png`）
  - `model_icon_haiseyin.png`（源自 `素材/海瑟音.png`）
  - `model_icon_ayuan_tishenban.png`（源自 `素材/阿元替身版.png`）
  - 游戏页附加资源放在 `public/assets/game/`，例如 `quick_assign_raccoon.png`（源自 `素材/小浣熊.png`，用于「一键分配」入口装饰）。
- 中文素材保留在 `素材/` 目录，仅作为构建输入，不被运行时直接引用。
- **中文昵称作为数据**由 TS 配置驱动（见 §14.11），不进文件名；运行时 UI 标签从 `MODEL_SLOTS` 读取。

### 14.4 大厅动图（ping-pong）

- 大厅首页以「大厅界面_动图」为主视觉，要求**正放→倒放→正放**无缝循环。
- 实现方式固定为「**预生成 ping-pong MP4**」：构建期由跨平台 Node 脚本 `scripts/build-lobby-pingpong.mjs` 调用 npm devDependency `ffmpeg-static` 提供的 ffmpeg 二进制，把原片正放 + 倒放拼接为单段 mp4；运行时只用 `<video autoplay muted loop playsInline>`。
- 脚本不依赖系统 ffmpeg，也不依赖 bash；`ffmpeg-static` 已覆盖 Linux / macOS / Windows × x64 / arm64。贡献者只需 `npm install && npm run assets:lobby` 即可重新生成 ping-pong mp4。
- 不允许使用 `playbackRate=-1`、`currentTime` 反向 seek 或运行时双 video 切换等替代方案（避免跨浏览器抖动与移动端发热）。
- 视频源固定为 `素材/大厅界面_动图.mp4`，构建产物固定为 `public/assets/lobby/lobby_pingpong.mp4`。
- 海报兜底：`public/assets/lobby/lobby_poster.jpg`，源自 `素材/大厅界面.jpg`。

### 14.5 音频控制（BGM 与音量）

- BGM 源固定为 `public/assets/lobby/lobby_bgm.mp3`（`素材/游戏大厅待机音乐.mp3`）。
- 进入大厅时音频元素 `muted=true` 自动播放（满足浏览器 autoplay policy）。
- **首次**用户交互（`pointerdown` 或 `keydown`）后立即解除静音并继续播放；解锁失败时（被浏览器拒绝）保持静音并 `console.warn`，不抛错。
- 用户可通过右上角浮动按钮在「有声 / 静音」之间切换。
- 不允许在未解锁前发声，不允许把 BGM 状态写入 `localStorage` 之外的任何来源（防止绕过 §3.1 单一事实源约束）。
- 用户可在系统设置弹窗里通过 0–100 整数滑块调节 BGM 音量；当前值持久化到 `localStorage` key `wolven_hunt.lobby.volume`（默认 80）。volume 与 muted 语义独立：滑到 0 不自动静音，按下静音按钮也不会清零 volume。
- muted 状态同样持久化到 `localStorage` key `wolven_hunt.lobby.muted`，刷新后保留。

### 14.6 大厅按钮

- 大厅下方水平显示三个按钮，从左到右顺序固定为：**开始游戏 → 历史复盘 → 系统设置**。
- 三张图标固定取自 `public/assets/lobby/btn_start.png` / `btn_history.png` / `btn_settings.png`。
- 第一阶段每个按钮 click 仍是 stub：`console.log('[lobby] click: start' | 'history' | 'settings')`；同时 `onAction(kind)` 必须接到统一弹窗状态（见 §14.10），由 `LobbyHome` 维护 `activeModal`，按 kind 切换打开 StartModal / HistoryModal / SettingsModal。
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

### 14.10 大厅弹窗层（Lobby Modal Layer）

- 大厅三个按钮（开始游戏 / 历史复盘 / 系统设置）共用一个通用弹窗外壳 `LobbyModal`，按 kind 切换内容（StartModal / HistoryModal / SettingsModal），同一时刻最多打开一个弹窗。
- 弹窗状态 `activeModal: 'start' | 'history' | 'settings' | null` 存放在 `LobbyHome` 内部 state；`LobbyButtons.onAction(kind)` 直接 `setActiveModal(kind)`。
- 弹窗背景固定为 `public/assets/lobby/settings_panel_bg.png`；弹窗主体通过 `createPortal` 挂载到 `document.body`。
- 关闭方式三选一：右上角 `<X />` 按钮、`Esc` 键、点击遮罩区。三种都调用 `onClose`。
- 打开时焦点进入弹窗，关闭时还原焦点；`role="dialog"`、`aria-modal="true"`、`aria-labelledby` 指向标题元素。
- 弹窗层 z-index 高于 lobby 视频 / shade / 按钮 / mute toggle，但仍属于前端壳，**不发起任何网络请求**。

### 14.11 模型配置存储（Model Configs）

- 系统设置弹窗内含 8 个模型 slot，每个 slot 由两部分组成：
  - **静态部分**（不进 `localStorage`）：`slot` 索引、中文 `nickname`、ASCII `iconPath`，统一定义在 `src/lib/modelConfigs.ts` 的 `MODEL_SLOTS` 常量数组。
  - **默认模型输入部分**：`baseUrl` / `apiKey` / `modelName` / `thinkingEnabled`，统一定义在 `src/lib/modelConfigs.ts` 的 `MODEL_CONFIG_DEFAULTS`，用于预填系统设置；8 个默认 slot 的 `thinkingEnabled` 固定为 `true`。
  - **用户覆盖部分**：用户在 UI 中修改的 `baseUrl` / `apiKey` / `modelName` / `thinkingEnabled`。
- 用户覆盖输入持久化到 `localStorage`，命名空间 `wolven_hunt.lobby.model_config.{slot}`，value 为 JSON `{baseUrl, apiKey, modelName, thinkingEnabled}`；不存在 key 时使用仓库默认配置显示。
- 读取旧版 `{baseUrl, apiKey, modelName}` 缓存时必须兼容：`thinkingEnabled` 缺失或不是 boolean 时回退对应 slot 的默认值。
- 写入采用 300ms debounce，避免每次按键打 storage；读 / 写失败仅 `console.warn`，不阻塞 UI。
- 第一阶段大厅页**不读出**这些字段进任何 fetch / WebSocket / SSE；模型条目仅作为 UI 占位。P2 FastAPI 接入时由后端读取并通过 spectator 视角脱敏（与 §14.1 不绕过 Referee 的硬约束一致）。
- API key 在前端源码默认值与 `localStorage` 用户覆盖值中均为明文；`<input type="password">` 仅是视觉掩码，不提供加密保护，文档中需提示风险。

### 14.12 弹窗内 CTA

- StartModal 含「进入游戏」CTA 按钮：第一阶段 `console.log('[lobby] enter game')` + 关闭弹窗（已在 STEP-02 落地）；STEP-03 改为调用 `onEnterGame()` 回调，触发 App 层级页面切换 + 过渡动画。
- HistoryModal 仅展示「功能开发中」占位文案，不放任何 CTA。
- SettingsModal 不含 CTA：所有改动通过受控输入实时 / debounce 写 `localStorage`，无「保存」按钮。

### 14.13 游戏准备页（Game Preparation Page）

- 应用顶层 `App.tsx` 维护 `page: 'lobby' | 'game'` 状态，配合 `phase: 'idle' | 'fade-out' | 'fade-in'` 过渡相控制全屏黑色 overlay 的显隐；不引入路由库。
- 进入游戏过渡：`fade-out`（600ms ease-in 渐黑）→ `setPage('game')` + 下一帧切到 `fade-in`（800ms ease-out 渐亮）→ `idle`。总时长 1.4s。
- 过渡触发时同步调用 `useLobbyAudio.toggleMute()` 静音 BGM（仅当当前未 muted）；不新增 fadeOut API。
- 游戏页布局：白天背景图全屏 cover，8 个席位分左右两列（左 4 / 右 4）垂直居中分布；席位圆圈使用 `clamp(60px, 8vw, 100px)` 响应式尺寸。
- 席位状态：空态显示圆形虚线边框 + lucide `Plus` 图标；已分配态显示模型头像 + 加粗昵称（昵称在圆圈外侧，左列右侧 / 右列左侧，白天背景下需增强文字阴影）。
- 席位编号：每个席位圆圈始终显示 1-based 编号徽标；左列自上而下 1–4 且徽标在左下角，右列自上而下 5–8 且徽标在右下角。编号仅是游戏准备页 UI 辅助，不进入 Referee / FSM / RuleEngine 边界。
- 席位身份位（`.game-seat-role`）本步骤为占位 `<span>`（`display: none`），留给后续步骤填充。
- 模型选择：点击席位（无论空态或已分配）→ 打开游戏页自有 `ModelPicker` 弹窗（不复用大厅 `LobbyModal` 或 `settings_panel_bg.png`）→ 列出 8 个模型卡片 → 已被其他席位占用的卡片主体置灰 + `disabled`，但在右下角显示图标型「交换」按钮；点击该图标只把当前席位模型与该模型所在席位互换，不产生重复 slot。当前席位已选项黄色边框高亮。
- 模型分配规则：每个 model slot 在 8 席位中至多出现一次；点击已分配头像可重新选择，旧 slot 释放回可选池。交换席位只调换 `assignments` 中两个位置，不写 `localStorage`、事件日志或 replay，也不清空按 model slot 记录的连通性测试结果。左下角显示小浣熊装饰入口（`quick_assign_raccoon.png`）与「一键分配」按钮，点击后仅在前端 UI 内用 Fisher-Yates 洗牌把 8 个 `MODEL_SLOTS` 随机分散到 8 个席位；该随机只影响当前页面内存中的 `assignments`，不写事件日志、不参与 replay、不进入 Referee / FSM / RuleEngine。触发后清空旧 `testResults` 与测试状态提示，用户需重新测试模型连通性。
- 游戏页本身**不持久化**席位分配到 `localStorage`，刷新页面后回大厅初始态（与 §14.1 不引入额外网络/状态边界一致）。
- 游戏页**不发起任何网络请求**，不引入游戏逻辑（FSM / Referee / RuleEngine），仅前端 UI 编排，与 §14.1 / §14.10 边界一致。
- 游戏准备页复用 `MODEL_SLOTS` 头像与昵称；模型 API 默认值只用于系统设置弹窗预填，不在本步骤用于席位分配或网络调用。

### 14.14 游戏内 UI 增强（Game Page Enhancements）

本节是 STEP-04 的契约。在 §14.13 游戏准备页基础上叠加：

- **顶栏右上**：固定两个 40×40 圆形按钮——规则（lucide `BookOpen`）+ 退出（lucide `X`），点规则打开 `RulesModal`，点退出打开 `ExitConfirmModal`。
- **规则弹窗**：`RulesModal` 不复用大厅 `settings_panel_bg.png` 背景图，使用游戏页自有弹窗面板与滚动正文背景承载规则文本；`rules.md` 仍作为唯一静态来源，但前端只做轻量 markdown 解析（标题 / 有序列表 / 无序列表 / 加粗），渲染成人类可读的结构化正文，不用 `<pre>` 直出 `#` 标记，不引入 markdown 富文本依赖。
- **顶部中心**：阶段指示器 `<StageIndicator />`，显示太阳/月亮（lucide `Sun` / `Moon`）+ `第{dayNumber}天` 文案。图标与文案必须垂直居中对齐。`stage: { dayNumber, phase }` 由 `GamePage` 内部 state 持有，初值 `{ dayNumber: 1, phase: 'day' }`，不写 `localStorage`。
- **白天 ↔ 黑夜过渡**：GamePage 内部独立的 `.game-stage-overlay`（z-index 4，作用域为 GamePage 内部，不复用 App 层级的 `.page-transition-overlay`），动画与进出大厅相同：600ms 黑屏 + 800ms 亮起。`bgSrc` 由 `stage.phase` 派生，黑屏期间 React re-render 自动换 `<img>` src。`transitionToStage(next: GameStage)` helper 触发动画。
- **中心聊天区**：`<GameChat />` 显示左右两栏永远并存——左 `通用聊天框`、右 `狼人聊天框`。两栏 `<input>` 本步骤 `disabled`（无消息总线）。狼人栏边框使用红色调以视觉区分。席位昵称显示在头像下方并限制宽度，聊天区夹在两列席位之间（当前 `left/right: clamp(118px, 25vw, 220px)`），底部预留操作区空间（当前 `bottom: clamp(200px, 20vh, 260px)`），在约 500px 宽 in-app browser 下也不得与昵称或底部按钮重叠。
- **底部按钮区** `<GameBottomActions />`：
  - "测试模型连通性" 按钮：8 席全部分配前 disabled；填满后启用，点击触发并行 LLM 测试。
  - "夜深了…" 按钮：8 席全部分配且全部测试 ✓ 前 disabled；点击触发 `transitionToStage({ dayNumber, phase: 'night' })`。
- **席位测试态**：`<GameSeat />` 新增 `testStatus?: ModelTestStatus` prop。`testing` 显示头像灰度 + 三点 pulse 动画（JSX 实现）；`pass` 显示绿色 ✓ 徽标（lucide `Check`）；`fail` 显示红色 ✗ 徽标（lucide `X`）。徽标位于圆圈右上角。
- **测试逻辑**：`src/lib/modelTest.ts` 提供 `testModelConnection(req)` 与 `readModelConfig(slot)`。`readModelConfig(slot)` 优先读取 `localStorage` 用户覆盖；没有用户覆盖时使用 `MODEL_CONFIG_DEFAULTS[slot]`，仅当有效 `baseUrl` / `apiKey` / `modelName` 缺失时返回 `null`，并兼容旧缓存的 `thinkingEnabled` 默认回退。GamePage `testResults: Record<number, ModelTestResult>` 与测试状态提示仅在内存（不写 localStorage）。改 `assignments` 时清除被覆盖 slot 的测试结果。测试中按钮文案显示为「正在测试中」，并至少展示一次可感知的 loading 态；测试完成后每个已分配 slot 必须落成 `pass` 或 `fail`，底部显示通过数量摘要。
- **退出流程**：点退出图标 → `ExitConfirmModal`（游戏页自有紧凑确认面板，不复用大厅 `settings_panel_bg.png`；含取消/确认两按钮）→ 确认后调 `onExitGame`（来自 App 层）→ App 反向过渡（600ms 黑屏 → `setPage('lobby')` → 800ms 亮起）。退出后不自动还原 BGM 静音状态；用户可手动取消静音。
- **倒计时**：本步骤暂不实现，留给后续步骤（如需要可由 GamePage 透传一个 `seconds` prop 给后续 `<CountdownBar />`）。
- **DEV-only [debug] 推进按钮**：`import.meta.env.DEV` 守卫；点击 `transitionToStage(...)` 切换白天/黑夜并自增 dayNumber，仅供开发期预览，生产 build tree-shake 掉。
- **网络请求豁免登记**（与 §14.1 "前端不发起 fetch / WebSocket / SSE" 的关系）：
  - **豁免 A — 同源静态资源 fetch**：`RulesModal` 通过 `fetch('/assets/game/rules.md')` 读取打包到 `public/` 的纯文本规则文档。属于浏览器对自身静态资源的请求（与 `<img>` / `<video>` 同性质），不构成跨域 / 后端 / LLM 调用，不破坏 §14.1 边界精神。
  - **豁免 B — 用户主动触发的 LLM 配置自检 fetch**：`testModelConnection` 仅在用户点击"测试模型连通性"按钮时执行；用 OpenAI 兼容协议（`POST {baseUrl}/chat/completions`，`Authorization: Bearer {apiKey}`，基础 body `{model, messages, max_tokens: 1}`），15s 超时。若该 slot `thinkingEnabled === true`，请求体按模型名追加思考模式字段：`qwen*` 用 `enable_thinking: true`；`kimi*` / `mimo*` / `deepseek*` / `glm*` / `doubao*` 用 `thinking: {type: "enabled"}`；`hy3*` 用 `chat_template_kwargs: {thinking: true, reasoning_effort: "medium"}`；`MiniMax*` 用 `reasoning_effort: "medium"`。若 `thinkingEnabled === false`，不发送任何 thinking / reasoning 附加字段。其用途是"配置自检"而非"游戏逻辑驱动"，不构成 PlayerView，不进事件日志，不参与胜负判定。P2 接入 FastAPI 后改走后端代理 `/api/test-model`，前端只发同域请求；STEP-04 直连仅是过渡方案。
  - 上述两类 fetch 不允许扩展到游戏逻辑、对局推进、聊天消息收发等任何运行时数据流；引擎相关交互必须等 P2 走 Referee。
  - 风险登记：apiKey 在 fetch header 中明文传输（HTTPS 下加密，HTTP 下泄漏）——文档需提示仅在 HTTPS 部署或本地 dev 使用。CORS 失败由用户感知为席位 ✗，不静默吞错。
