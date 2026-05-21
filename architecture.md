# Wolven Hunt Architecture Contract

本文档是 `plan.md` 的第一阶段落地版。后续实现必须以 `plan.md` 为基准，并以本文档作为首期架构契约。若两者发生冲突，先更新 `plan.md`，再同步本文档和代码。

## 1. Scope

首期目标是一个可复现、配置驱动、事件日志为单一事实源的 8 人狼人杀引擎骨架。

首期固定板子：

- 狼人 3 人
- 村民 2 人
- 预言家 1 人
- 骑士 1 人
- 守卫 1 人

首期不实现真实业务代码。第一阶段只冻结目录、配置模板、状态机、事件 schema、权限边界、异常 fallback、replay 模式和测试边界。

## 2. Rule Contract

`GameConfig = RolePack + RuleSet + ModelRoster + PromptPack + random_seed`

新增板子时只能通过配置扩展，不改核心引擎代码。每局 `game_start` 必须记录：

- `random_seed`
- `config_hash`
- `seat_range`
- `role_assignment`

这些 metadata 用于 replay 校验。进入 PlayerView 前必须由 Referee 脱敏。

座位统一使用 1-based 编号，首版固定为 1 到 8 号。`GAME_START` 使用 `random_seed` 派生的 deterministic RNG 洗牌分配角色。玩家只知道自己的角色；狼人额外知道全部狼队同伴身份；spectator 不暴露隐藏身份。

## 3. Win Condition

每次夜晚结算、骑士挑战、投票放逐后立即执行胜负检查。

狼人胜：

- `alive_wolves > alive_good_players`
- 或 `alive_good_players == 0`

好人胜：

- `alive_wolves == 0`

胜负规则写入 `configs/games/_rule_sets/majority_or_massacre_all.yaml`。

## 4. Roles

### Seer

- 每晚查验一名玩家。
- 可以查验死亡玩家。
- 不可查验自己。
- 只返回阵营：`wolf` 或 `good`。
- 生成 `seer_check_result` 私有事件，仅预言家本人可见。
- 预言家死亡后不再被调用。
- 允许重复查验同一玩家。

### Guard

- 首夜可守。
- 可自守。
- 不可连续两晚守同一目标，包括首夜到第二夜。
- 非法目标由 Referee 在 `validate_action` 阶段拒绝并要求重选。
- 狼刀被守护时生成公开 `no_death_tonight` 事件，但不暴露原因。

### Wolves

- 每晚最多 1 轮夜聊，每狼一句。
- 随后同时提交刀人目标。
- 多数决定刀人目标。
- 平票时在被狼队投到的目标中 deterministic random 选择，并记录 `wolf_tie_random`。
- 合法刀人目标是所有存活非狼玩家。
- 不允许自刀、不允许刀狼队友、不允许空刀。
- 狼队夜聊和投刀事件仅狼队可见。

### Knight

- 白天投票开始前任意时间可发动一次。
- 首日可发动。
- 夜晚不能发动。
- 投票已经开始后不能插入发动。
- 挑战目标必须是当日存活玩家，不能是自己。
- 挑中狼人：目标当场死亡；目标无遗言。
- 挑中好人：骑士死亡；骑士有遗言。
- 发动后跳过当日剩余发言与投票；若游戏未结束，直接进入夜晚。
- 每局最多发动一次。

### Villager

- 无夜晚主动技能。
- 白天参与发言、投票、PK 重投和公开流程。

## 5. Day, Vote, Last Words

首夜可以死亡，`first_night_can_die: true` 是首版默认。

首夜死亡在首日 `DAY_ANNOUNCE` 公示。只有首夜被刀死亡者进入首日 `DAY_LAST_WORDS`。第二夜及之后的夜晚死亡者无遗言。

白天按座位顺序一轮发言，每名存活玩家一次，中文默认 300 字上限。

投票规则：

- 同时投票。
- 公开票型。
- 不允许弃票。
- 不允许改票。
- 无警长。
- 首轮投票只能投存活玩家。
- 允许投自己。
- 不能投已死亡玩家。

首轮平票进入 `DAY_VOTE_PK`。平票玩家各一次 PK 发言后重投。PK 重投只能投 PK 台上的存活玩家，PK 台上玩家不参与重投。第二次仍平票则平安日，直接入夜。

有遗言：

- 白天被放逐者
- 骑士挑战错误死亡的骑士
- 首夜被刀死亡者

无遗言：

- 第二夜及之后的夜晚死亡者
- 被骑士挑战死亡的狼人

## 6. Agent Lifecycle

死亡 Agent 停止被调用决策。

默认 PlayerView 冻结到死亡公示事件之前的所有可见事件，加上死亡公示本身。死亡后仍接收全局公开事件，包括后续公示、放逐结果和胜负结果，保证 replay 时死亡玩家也能理解游戏走向。

调试模式可以让死亡 Agent 继续接收所有公开事件，用于评测。

## 7. FSM Contract

FSM 子状态必须显式拆细，并与事件日志一一对应。

```text
GAME_START
  -> NIGHT_START
    -> NIGHT_GUARD
    -> NIGHT_WOLF_CHAT
    -> NIGHT_WOLF_VOTE
    -> NIGHT_SEER
    -> NIGHT_RESOLVE
    -> CHECK_WIN
  -> DAY_ANNOUNCE
    -> DAY_LAST_WORDS?
    -> DAY_SPEECH
    -> DAY_KNIGHT_INTERRUPT?
    -> DAY_VOTE
    -> DAY_VOTE_PK?
    -> DAY_EXILE?
    -> CHECK_WIN
  -> loop NIGHT_START
GAME_END
```

骑士窗口不是固定线性子状态，而是 `DAY_ANNOUNCE` 结束后到 `DAY_VOTE` 开始前的可中断动作。若触发，FSM 暂停当前白天流程，结算骑士决斗和胜负。若未结束，跳过当日剩余白天流程并进入夜晚。

## 8. Night Resolve

`NIGHT_RESOLVE` 顺序固定：

1. 读取本晚守卫目标 `G`、狼刀目标 `K`、预言家目标 `S`。
2. 若 `G == K`，生成 `no_death_tonight`。
3. 若 `G != K`，`K` 死亡，生成 `death_at_night`。
4. 首夜死亡会在首日 `DAY_ANNOUNCE` 公示并触发 `DAY_LAST_WORDS`。
5. 第二夜及之后夜死无遗言。
6. `seer_check_result` 在 `NIGHT_SEER` 结束时已生成，结算阶段不再处理。
7. 死亡事件不暴露死因。

同夜信息可见性：

- 狼人不知道今晚是否被守。
- 预言家查验结果在 `NIGHT_SEER` 结束时立即对本人可见。
- 守卫不知道自己是否守住狼刀。

## 9. Event Log

事件日志是单一事实源。所有 PlayerView、回放、胜负判定都从事件日志派生。

事件必须 append-only、不可变、全局 `seq` 单调递增。每个事件携带 `schema_version`。

公共字段：

```json
{
  "event_id": "uuid",
  "schema_version": "1.0",
  "game_id": "uuid",
  "seq": 1,
  "phase": "NIGHT_GUARD",
  "day": 1,
  "timestamp": "iso8601",
  "type": "guard_protect",
  "actor": 6,
  "visibility": {
    "public": false,
    "seats": [6]
  },
  "payload": {}
}
```

事件类型 v1.0：

- 流程：`game_start`, `phase_enter`, `phase_exit`, `game_end`
- 夜晚：`guard_protect`, `wolf_chat_message`, `wolf_kill_vote`, `wolf_kill_decided`, `wolf_tie_random`, `seer_check`, `seer_check_result`, `no_death_tonight`, `death_at_night`
- 白天：`day_announce`, `last_words`, `speech`, `knight_challenge`, `knight_result`, `vote_cast`, `vote_result`, `vote_pk_enter`, `peaceful_day`, `exile`
- 系统：`win_check`, `agent_timeout`, `agent_invalid_action`, `agent_fallback_triggered`
- 元数据：`llm_call`

`llm_call` 包含 prompt hash、raw response hash、storage ref、model、token、cost，但仅写入存储层，不进入 PlayerView。完整 raw response 仅写入私有存储。

所有随机事件 payload 必须记录：

- `rng_stream`
- `candidates`
- `selected`
- `reason`

## 10. Visibility

可见性由 Referee 统一处理。

- 公共事件：所有玩家可见，包括死亡 Agent。
- 狼队事件：仅狼队 seat 可见。
- 私有事件：仅 actor 或白名单 seat 可见。
- `llm_call`、完整 `role_assignment`、raw response 存储引用默认不进入任何 PlayerView。

PlayerView 中的 `game_start` 必须脱敏：

- 本人看到自己的角色。
- 狼人看到狼队同伴。
- spectator 不看到隐藏身份。

Referee 是唯一权限边界。核心规则和 Agent 不得自行拼接越权视角。

## 11. LLM Errors and Fallback

三类异常：

- 超时：单次调用超过 `llm.timeout_seconds`。
- 非法 JSON 或 schema 校验失败。
- 合法性校验失败：结构合法但违反规则。

每阶段每 Agent 最多重试 `llm.max_retries` 次，默认 2 次。重试仍失败则触发 fallback，并记录 `agent_fallback_triggered`。

默认 fallback：

| 阶段 | Fallback |
|---|---|
| `NIGHT_GUARD` | 随机选一个合法目标，排除昨晚守护对象 |
| `NIGHT_WOLF_CHAT` | 发送空消息，占位为 `[沉默]` |
| `NIGHT_WOLF_VOTE` | 随机选一个合法目标 |
| `NIGHT_SEER` | 随机选一个非自己玩家 |
| `DAY_SPEECH` | 默认模板 `我没有更多信息` |
| `DAY_KNIGHT_INTERRUPT` | 默认不发动 |
| `DAY_VOTE` | 随机选一个存活玩家，允许自己 |
| `DAY_VOTE_PK` | 台下玩家随机投一个 PK 台上存活玩家；如无台下玩家可投，直接平安日 |
| `DAY_LAST_WORDS` | 默认模板 `我没有遗言` |

所有 fallback 行为写入 RuleSet。所有 fallback 随机使用 deterministic RNG，并记录候选集、选中值与 fallback 原因。

## 12. Replay

首期定义两种 replay 模式。

`replay_deterministic`：

- 从事件日志直接渲染时间线。
- 不调用 LLM。
- 用于 UI 复盘、教学和争议复核。

`replay_resimulate`：

- 使用存储的 `llm_call` 原始响应重跑 FSM。
- 断言事件序列与原日志一致。
- 用于回归测试和引擎重构后的等价性验证。

所有随机决策必须可由 `random_seed + rng_stream + candidates` 重建。事件记录的 `selected` 用于一致性断言。

## 13. Prompt and Injection Defense

Prompt 模板文件名必须带版本号，例如：

```text
configs/prompts/zh/seer/night_action.v1.md
configs/prompts/zh/seer/night_action.v3.md
```

事件日志记录 `prompt_version`，保证修改 prompt 后旧日志仍可解释。

输入侧：

- Referee 不审查 Agent 发言内容。
- Referee 只保证注入 prompt 的私有信息正确脱敏。
- 发言中声称拥有不存在的信息属于合法角色扮演。
- 泄漏测试覆盖预言家结果、狼队身份、守卫目标。

输出侧：

- 所有 LLM 输出走结构化 schema 校验。
- 校验失败进入重试与 fallback。

PlayerView 大小控制：

- 使用最近事件窗口加确定性历史摘要。
- 摘要算法必须是基于事件日志的纯函数。
- 单局 token 上限通过 `llm.budget_per_game` 配置。

## 14. Module Boundaries

目录职责：

- `src/wolven_hunt/core`：GameState、Event、Role、RuleEngine、WinCondition。
- `src/wolven_hunt/referee`：PlayerView、visibility filter、validate_action。
- `src/wolven_hunt/orchestration`：纯 Python FSM；后续 LangGraph adapter 只作为边界层。
- `src/wolven_hunt/agents`：PlayerInterface、LLMPlayer、HumanPlayer stub。
- `src/wolven_hunt/llm`：LiteLLM 网关、structured output、重试、fallback、成本记录。
- `src/wolven_hunt/storage`：事件日志、快照、两种 replay 模式。
- `src/wolven_hunt/api`：FastAPI 控制接口，P2 实现。

调用链固定：

```text
FSM
  -> Referee.build_view
  -> PlayerInterface.decide
  -> structured schema validation
  -> Referee.validate_action
  -> RuleEngine.apply
  -> EventLog.append
```

`RuleEngine.apply(state, action) -> (new_state, events)` 必须保持纯函数。不读取 PlayerView，不直接调用 LLM，不处理权限过滤。

## 15. API Boundary

FastAPI 属于 P2，不在第一阶段实现。边界先冻结：

- `POST /games`
- `GET /games/{id}`
- `GET /games/{id}/events`
- `POST /games/{id}/run`
- `POST /games/{id}/pause`
- `POST /games/{id}/resume`
- `POST /games/{id}/replay`
- `POST /games/{id}/dev/inject`
- `GET /games/{id}/stream`

所有读取接口默认返回 spectator 脱敏视角。

## 16. Test Contract

测试目录按 `plan.md` 固定：

- `tests/unit`：RuleEngine 纯函数单测。
- `tests/integration`：FSM 全流程。
- `tests/leakage`：PlayerView 脱敏。
- `tests/golden`：固定 seed 加 mock Agent 黄金回放。
- `tests/property`：Hypothesis 不变量。

必须覆盖：

- 预言家查活人、死人、重复查验、死亡后停用、不能查自己。
- 胜负三条规则和每个检查点。
- 首夜死亡遗言、第二夜后夜死无遗言、守卫平安夜、PK、二次平票、骑士挑战。
- 死亡 Agent 停用但仍接收公开事件。
- LLM 异常、重试、fallback。
- 固定 seed 下 replay deterministic 与 resimulate 一致。
- PlayerView 不包含 visibility 白名单外事件。

## 17. Change Control

`plan.md` 是项目基准。任何后续实现若需要改变规则、状态机、事件 schema、目录边界、配置字段、prompt 版本策略、fallback 或 replay 语义，必须同步更新 `plan.md`。

普通代码变更也必须检查 `plan.md` 是否需要同步记录。若无需更新，应在提交说明或变更说明中明确该变更只是落实现有计划，不改变项目契约。

## 18. Web Shell Boundary

本节是 `plan.md` §14「前端入口骨架（Web Lobby Shell）」的契约落地。前端壳与 Python 引擎在同一仓库共存，但权限边界、数据流与命名空间必须严格切开。

### 18.1 模块边界

- 前端入口壳的源码位于仓库根目录：`package.json`、`package-lock.json`、`index.html`、`vite.config.ts`、`tsconfig.json`、`tsconfig.node.json`、`src/components/`、`src/hooks/`、`src/main.tsx`、`src/App.tsx`、`src/styles.css`、`public/`。
- 与 `src/wolven_hunt/*` 双向不导入：前端不得引用 `src/wolven_hunt/*` 或 `configs/*`；Python 引擎不得依赖前端代码。
- 前端只消费 spectator 脱敏视角。任何玩家视角、行动校验、私有信息均通过 §15 FastAPI 边界（P2 实现）；前端**不得绕过 Referee**。
- 第一阶段大厅页**没有任何后端调用**：纯静态资源 + UI 状态，不发起 HTTP / WebSocket / SSE 请求。

### 18.2 前端栈

- Vite + React 18 + TypeScript。
- 使用 npm 管理依赖，`package-lock.json` 必须随 `package.json` 提交以保证安装可复现。
- 图标使用 `lucide-react`。
- 不引入额外的 CSS 框架；不引入路由库（按钮 click 仅 stub）。

### 18.3 静态资源命名与构建

- 运行时资源放在 `public/assets/lobby/`，文件名 ASCII 小写蛇形：`lobby_pingpong.mp4`、`lobby_bgm.mp3`、`lobby_poster.jpg`、`btn_start.png`、`btn_history.png`、`btn_settings.png`。
- 中文素材保留在 `素材/`，仅作为构建输入，不被运行时直接引用。
- ping-pong 视频以脚本可复现方式生成：`scripts/build-lobby-pingpong.mjs` 是跨平台 Node 脚本，通过 npm devDependency `ffmpeg-static` 提供的 ffmpeg 二进制把 `素材/大厅界面_动图.mp4` 正放 + 倒放拼接为 `public/assets/lobby/lobby_pingpong.mp4`。脚本不依赖系统 ffmpeg 与 bash；`ffmpeg-static` 已覆盖 Linux / macOS / Windows × x64 / arm64。
- 第一阶段的 ping-pong 产物 `public/assets/lobby/lobby_pingpong.mp4` 随仓库提交，确保 `git clone && npm install && npm run dev` 即可启动；脚本只在替换素材时重跑。替换素材时以重跑脚本为唯一路径，不得依赖不可重建产物。

### 18.4 大厅动图

- 实现方式固定为预生成 ping-pong MP4，运行时仅用 `<video autoplay muted loop playsInline>`。
- 禁止使用 `playbackRate=-1`、`currentTime` 反向 seek、运行时双 video 切换等替代方案。

### 18.5 BGM 自动播放策略

- 初始 `muted=true` 自动播放。
- **首次**用户交互（`pointerdown` 或 `keydown`）后立即解除静音并继续播放；解锁失败保持静音并 `console.warn`，不抛错。
- 用户可通过右上角浮动按钮在「有声 / 静音」之间切换。
- 不允许在未解锁前发声；不允许把 BGM 状态写入 `localStorage` 之外的任何来源。

### 18.6 大厅按钮

- 大厅下方水平显示三个按钮，从左到右：开始游戏 → 历史复盘 → 系统设置。
- 三张图标固定取自 §18.3 命名的 PNG。
- 第一阶段 click 仅 stub（`console.log('[lobby] click: start|history|settings')`），并暴露可选回调 `onAction(kind)` 供后续步骤接入。
- `<button>` 可键盘聚焦；`aria-label` 与 `<img alt>` 使用中文按钮名。

### 18.7 行为禁区

第一阶段大厅页代码**不允许**包含：

- LLM 调用、随机数、规则判定、角色分配、投票、FSM 关键字。
- 直接读取 `src/wolven_hunt/*`、`configs/*`、事件日志或 game state。
- HTTP / WebSocket / SSE / Worker 请求。
- 写入 `localStorage` 以外的持久化存储。

### 18.8 阶段交付规格

每个阶段的执行规格放在 `docs/specs/STEP-{NN}-{slug}.md`，由本仓库代理写入，作为实施手册与验收指标的镜像。第一阶段对应 `docs/specs/STEP-01-lobby-home.md`。
