# Wolven Hunt Architecture Contract

本文档是 `plan.md` 的架构契约落地版。后续实现必须以 `plan.md` 为基准，并以本文档作为首期架构契约。若两者发生冲突，先更新 `plan.md`，再同步本文档和代码。

## 1. Scope

首期目标是一个可复现、配置驱动、事件日志为单一事实源的 8 人狼人杀引擎骨架。

首期固定板子：

- 狼人 3 人
- 村民 2 人
- 预言家 1 人
- 骑士 1 人
- 守卫 1 人

当前阶段为 STEP-07 / P3 观赛 MVP：允许在 STEP-06 外部接入基础上实现 per-seat LLM provider 路由、观赛 pacing/ack、叙事化事件流、角色揭晓、前端音视频、倒计时、投票直方图、骑士决斗视频与结局浮层。

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

- 流程：`game_start`, `phase_enter`, `phase_exit`, `game_end`, `role_reveal`
- 夜晚：`guard_protect`, `wolf_chat_message`, `wolf_kill_vote`, `wolf_kill_decided`, `wolf_tie_random`, `seer_check`, `seer_check_result`, `no_death_tonight`, `death_at_night`
- 白天：`day_announce`, `last_words`, `speech`, `knight_challenge`, `knight_result`, `vote_cast`, `vote_result`, `vote_pk_enter`, `peaceful_day`, `exile`
- 系统：`win_check`, `agent_timeout`, `agent_invalid_action`, `agent_fallback_triggered`, `agent_budget_warning`
- 元数据：`llm_call`

`llm_call` 包含 `prompt_hash`、`raw_response_hash`、`storage_ref`、`model`、`prompt_tokens`、`completion_tokens`、`cost_usd`、`prompt_version`，但仅写入存储层，不进入 PlayerView。完整 raw response 仅写入私有存储；`llm_call` payload 不得包含 raw response 原文。

`role_reveal` 仅在 `GAME_END` 后由 Referee 生成，公开可见，payload 固定为 `{winner, seats: [{seat, role, alive}], highlights}`。`pacing_tick` 是未来保留事件；STEP-07 不写入事件日志，避免污染 replay hash。

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

错误子类映射到外显事件：`timeout` / `rate_limit` / `network` 归为 `agent_timeout`；`invalid_json` / `schema_violation` / `illegal_action` 归为 `agent_invalid_action`。

每阶段每 Agent 最多重试 `llm.max_retries` 次，默认 2 次。重试 prompt 末尾追加：`上一次输出未被接受：{error_type}: {message}。请只返回符合 schema 的 JSON。` 重试仍失败则触发 fallback，并记录 `agent_fallback_triggered`。

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
- 一致性比对维度固定为 `type, actor, day, phase, canonical_payload`；不要求 `event_id` 与 `timestamp` 字节相等。首个分歧报告 `(seq, field, expected, actual)`。

所有随机决策必须可由 `random_seed + rng_stream + candidates` 重建。事件记录的 `selected` 用于一致性断言。

## 13. Prompt and Injection Defense

Prompt 模板文件名必须带版本号，例如：

```text
configs/prompts/zh/seer/night_action.v1.md
configs/prompts/zh/seer/night_action.v3.md
```

事件日志记录 `prompt_version`，保证修改 prompt 后旧日志仍可解释。

提示词渲染顺序固定为：

```text
[system.v1.md] + [role/phase.v1.md] + [JSON payload] + [retry_error?]
```

`system.v1.md` 是全员统一系统提示词，包含规则摘要、信息边界和 JSON-only 输出契约。角色/phase 模板来自 `configs/prompts/{language}/{role}/{kind}.{version}.md`。`JSON payload` 只包含 seat、role、phase、rule_set_summary、teammates、Referee 过滤后的 visible_events 和 output_schema。LLM 重试时只在末尾追加结构化错误说明。

输入侧：

- Referee 不审查 Agent 发言内容。
- Referee 只保证注入 prompt 的私有信息正确脱敏。
- 发言中声称拥有不存在的信息属于合法角色扮演。
- 泄漏测试覆盖预言家结果、狼队身份、守卫目标。

输出侧：

- 所有 LLM 输出走结构化 schema 校验。
- 校验失败进入重试与 fallback。
- 输出 JSON schema 按 phase 固定为：`NIGHT_GUARD {target}`、`NIGHT_WOLF_CHAT {text}`、`NIGHT_WOLF_VOTE {target}`、`NIGHT_SEER {target}`、`DAY_SPEECH {text}`、`DAY_KNIGHT_INTERRUPT {activate, target?}`、`DAY_VOTE {target}`、`DAY_VOTE_PK {target}`、`DAY_LAST_WORDS {text}`。

PlayerView 大小控制 / 上下文管理策略：

- Prompt 上下文只从 Referee 过滤后的 `PlayerView.visible_events` 构造。
- 默认使用最近 40 条事件，并强制保留 `game_start`、`death_at_night`、`exile`、`knight_result`、`seer_check_result`。
- 当可见事件超过 60 条时，payload 使用首 10 条事件 + 中间摘要 + 最近 30 条事件。
- 摘要格式固定为 `{type, day, phase, actor, summary_text}`，其中 `type` 为 `summary`。
- 摘要算法必须是基于可见事件的纯函数，不调用 LLM，不改变 EventLog、replay hash 或权限边界。
- 单局 token 上限通过 `llm.budget_per_game` 配置。

Prompt 存储：

- `raw_responses.jsonl` 只保存 `prompt_hash` 与 `prompt_version`，不保存 prompt 原文。
- prompt 内容正确性通过测试捕获 provider 入参验证；公开事件、PlayerView、spectator API 和 SSE 均不返回 prompt 原文。

## 14. Module Boundaries

目录职责：

- `src/wolven_hunt/core`：GameState、Event、Role、RuleEngine、WinCondition。
- `src/wolven_hunt/referee`：PlayerView、visibility filter、validate_action。
- `src/wolven_hunt/orchestration`：纯 Python FSM；后续 LangGraph adapter 只作为边界层。
- `src/wolven_hunt/agents`：PlayerInterface、LLMPlayer、HumanPlayer stub。
- `src/wolven_hunt/llm`：LiteLLM 网关、structured output、重试、fallback、成本记录。
- `src/wolven_hunt/storage`：事件日志、快照、两种 replay 模式。
- `src/wolven_hunt/api`：FastAPI 控制接口，STEP-06 实现。

落盘目录固定为 `runs/{game_id}/events.jsonl`、`raw_responses.jsonl`、`manifest.json`、`cost.jsonl`、`narrative.jsonl`、`final_reveal.json`。写入使用 tmp + fsync + atomic rename 或行级 fsync，文件权限为 `0600`。

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

FastAPI 在 STEP-06 实现，所有读取接口默认返回 spectator 脱敏视角：

- `POST /games`
- `GET /games/{id}`
- `GET /games/{id}/events`
- `POST /games/{id}/run`
- `POST /games/{id}/pause`
- `POST /games/{id}/resume`
- `POST /games/{id}/replay`
- `POST /games/{id}/dev/inject`
- `GET /games/{id}/stream`
- `GET /games/{id}/narrative`
- `GET /games/{id}/reveal`
- `POST /games/{id}/ack`
- `POST /games/{id}/speech`
- `POST /games/{id}/wolf_chat`

错误体统一为 `{code, message, details?}`。`speech` 与 `wolf_chat` 端点仍走 Referee `validate_action`，前端不得自行绕过合法性校验。

SSE 线协议固定为 `event: game_event`、`id: <seq>`、`data: <spectator Event JSON>`；STEP-07 额外推送同源 `event: narrative_row`，与 `game_event` 共享原始事件 `seq`。每 30s 发送 `event: heartbeat`。`Last-Event-ID` 表示从 `seq + 1` 续推，不存在则返回 410。CORS 默认白名单是 `http://localhost:5173`，可通过 `WH_API_CORS_ORIGINS` 配置。

STEP-06 环境变量统一由 `src/wolven_hunt/config/settings.py` 的 `pydantic-settings.BaseSettings` 读取：

- `WH_LLM_PROVIDER`：`mock` | `litellm`，缺省为 `mock`；非法值启动失败
- `WH_LLM_API_KEY`：真实 provider 的 API key；`WH_LLM_PROVIDER=litellm` 时必填
- `WH_LLM_BASE_URL`：LiteLLM base URL，可选
- `WH_LLM_MODEL`：默认模型名，可选
- `WH_LLM_TIMEOUT_SECONDS`：单次调用超时，默认 30
- `WH_LLM_MAX_RETRIES`：重试预算，默认 2
- `WH_LLM_BUDGET_PER_GAME`：单局 token 上限，默认 100000；超限时发一次 `agent_budget_warning`，游戏继续运行
- `WH_LLM_PROVIDER_MAP`：空字符串或 YAML 路径；非空时按座位路由 provider，缺失座位回退到全局 `WH_LLM_*`
- `WH_PACING_PROFILE`：`live | fast | off`，默认 `live`；CI / replay / resimulate 强制 `off`
- `WH_PACING_PHASE_MS`：phase 切换基础停顿，默认 600
- `WH_PACING_SPEECH_MS`：speech / wolf_chat / last_words 后停顿，默认 400
- `WH_PACING_NIGHT_MS`：进入夜晚的额外停顿，默认 1000
- `WH_PACING_ACK_TIMEOUT_MS`：现场观赛 ack 最大等待时间，默认 15000；ack 超时只解除等待，不写 EventLog
- `WH_RUNS_DIR`：落盘根目录，默认 `./runs`
- `WH_API_HOST`：FastAPI 监听地址，默认 `127.0.0.1`
- `WH_API_PORT`：FastAPI 监听端口，默认 8000
- `WH_API_CORS_ORIGINS`：CORS 白名单，逗号分隔，默认 `http://localhost:5173`

`.env` 已在 `.gitignore`；`.env.example` 列出全部变量（不含真值）。CI 使用 `WH_LLM_PROVIDER=mock`，不消耗 API key。

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
- 固定 seed 下 `replay_deterministic` 一致；`replay_resimulate` 使用 raw LLM response 校验事件序列等价。
- CI 一律 mock provider；真实模型 smoke 不进入默认 pytest。
- PlayerView 不包含 visibility 白名单外事件。

## 17. Change Control

`plan.md` 是项目基准。任何后续实现若需要改变规则、状态机、事件 schema、目录边界、配置字段、prompt 版本策略、fallback 或 replay 语义，必须同步更新 `plan.md`。

普通代码变更也必须检查 `plan.md` 是否需要同步记录。若无需更新，应在提交说明或变更说明中明确该变更只是落实现有计划，不改变项目契约。

## 17.1 Provider 路由与节奏

STEP-07 新增 per-seat provider map 契约：`ProviderMap = dict[seat_number, ProviderConfig]`。未指定座位回退到 YAML default，再回退到全局 `WH_LLM_*`。ProviderConfig 只决定调用哪个模型，不进入事件日志、narrative、PlayerView、spectator API 或 SSE。

STEP-07 新增 `PacingController`，由运行时在事件发布后调用；`profile=off` 时为 no-op。现场观赛 audio/video 通过 `POST /games/{id}/ack` 解除等待；ack 不进入 EventLog、不影响 replay hash，超时只解除等待。

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

- 运行时资源放在 `public/assets/lobby/` 与 `public/assets/game/`，文件名 ASCII 小写蛇形：`lobby_pingpong.mp4`、`lobby_bgm.mp3`、`lobby_poster.jpg`、`btn_start.png`、`btn_history.png`、`btn_settings.png`、`settings_panel_bg.png`、`model_icon_minimax_laoshi.png`、`model_icon_wanwen.png`、`model_icon_guangzhimingmian.png`、`model_icon_dami.png`、`model_icon_xueba.png`、`model_icon_xiaodoubao.png`、`model_icon_haiseyin.png`、`model_icon_ayuan_tishenban.png`、`quick_assign_raccoon.png`（源自 `素材/小浣熊.png`）。
- 中文素材保留在 `素材/`，仅作为构建输入，不被运行时直接引用。
- **中文昵称作为数据**由 TS 配置驱动（见 §18.10），不进文件名；运行时 UI 标签从 `MODEL_SLOTS` 读取。
- ping-pong 视频以脚本可复现方式生成：`scripts/build-lobby-pingpong.mjs` 是跨平台 Node 脚本，通过 npm devDependency `ffmpeg-static` 提供的 ffmpeg 二进制把 `素材/大厅界面_动图.mp4` 正放 + 倒放拼接为 `public/assets/lobby/lobby_pingpong.mp4`。脚本不依赖系统 ffmpeg 与 bash；`ffmpeg-static` 已覆盖 Linux / macOS / Windows × x64 / arm64。
- 第一阶段的 ping-pong 产物 `public/assets/lobby/lobby_pingpong.mp4` 随仓库提交，确保 `git clone && npm install && npm run dev` 即可启动；脚本只在替换素材时重跑。替换素材时以重跑脚本为唯一路径，不得依赖不可重建产物。

### 18.4 大厅动图

- 实现方式固定为预生成 ping-pong MP4，运行时仅用 `<video autoplay muted loop playsInline>`。
- 禁止使用 `playbackRate=-1`、`currentTime` 反向 seek、运行时双 video 切换等替代方案。

### 18.5 音频控制（BGM 与音量）

- 初始 `muted=true` 自动播放。
- **首次**用户交互（`pointerdown` 或 `keydown`）后立即解除静音并继续播放；解锁失败保持静音并 `console.warn`，不抛错。
- 用户可通过右上角浮动按钮在「有声 / 静音」之间切换。
- 用户可在系统设置弹窗里通过 0–100 整数滑块调节 BGM 音量；当前值持久化到 `localStorage` key `wolven_hunt.lobby.volume`（默认 80）。volume 与 muted 语义独立：滑到 0 不自动静音，按下静音按钮也不会清零 volume。
- muted 状态同样持久化到 `localStorage` key `wolven_hunt.lobby.muted`，刷新后保留。
- 不允许在未解锁前发声；不允许把 BGM 状态写入 `localStorage` 之外的任何来源。

### 18.6 大厅按钮

- 大厅下方水平显示三个按钮，从左到右：开始游戏 → 历史复盘 → 系统设置。
- 三张图标固定取自 §18.3 命名的 PNG。
- 第一阶段 click 仍是 stub（`console.log('[lobby] click: start|history|settings')`）；同时 `onAction(kind)` 必须接到统一弹窗状态（见 §18.9），由 `LobbyHome` 维护 `activeModal`，按 kind 切换打开 StartModal / HistoryModal / SettingsModal。
- `<button>` 可键盘聚焦；`aria-label` 与 `<img alt>` 使用中文按钮名。

### 18.7 行为禁区

第一阶段大厅页代码**不允许**包含：

- LLM 调用、随机数、规则判定、角色分配、投票、FSM 关键字。
- 直接读取 `src/wolven_hunt/*`、`configs/*`、事件日志或 game state。
- HTTP / WebSocket / SSE / Worker 请求。
- 写入 `localStorage` 以外的持久化存储。

### 18.8 阶段交付规格

每个阶段的执行规格放在 `docs/specs/STEP-{NN}-{slug}.md`，由本仓库代理写入，作为实施手册与验收指标的镜像。第一阶段对应 `docs/specs/STEP-01-lobby-home.md`，第二阶段对应 `docs/specs/STEP-02-lobby-modal-and-settings.md`。

### 18.9 大厅弹窗层（Lobby Modal Layer）

- 大厅三个按钮（开始游戏 / 历史复盘 / 系统设置）共用通用弹窗外壳 `LobbyModal`，按 kind 切换内容（StartModal / HistoryModal / SettingsModal），同一时刻最多打开一个弹窗。
- 弹窗状态 `activeModal: 'start' | 'history' | 'settings' | null` 存放在 `LobbyHome`；`LobbyButtons.onAction(kind)` 直接 `setActiveModal(kind)`。
- 弹窗背景固定为 `public/assets/lobby/settings_panel_bg.png`；弹窗主体通过 `createPortal` 挂载到 `document.body`。
- 关闭方式三选一：右上角 `<X />` 按钮、`Esc` 键、点击遮罩区。三种都调用 `onClose`。
- 打开时焦点进入弹窗，关闭时还原焦点；`role="dialog"`、`aria-modal="true"`、`aria-labelledby` 指向标题元素。
- 弹窗层 z-index 高于 lobby 视频 / shade / 按钮 / mute toggle，但仍属于前端壳，**不发起任何网络请求**（与 §18.1 / §18.7 一致）。

### 18.10 模型配置存储（Model Configs）

- 系统设置弹窗内含 8 个模型 slot。每个 slot 由两部分组成：
  - **静态部分**（不进 `localStorage`）：`slot` 索引、中文 `nickname`、ASCII `iconPath`，统一定义在 `src/lib/modelConfigs.ts` 的 `MODEL_SLOTS` 常量数组。
  - **默认模型输入部分**：`baseUrl` / `apiKey` / `modelName` / `thinkingEnabled`，统一定义在 `src/lib/modelConfigs.ts` 的 `MODEL_CONFIG_DEFAULTS`，用于预填系统设置；8 个默认 slot 的 `thinkingEnabled` 固定为 `true`。
  - **用户覆盖部分**：用户在 UI 中修改的 `baseUrl` / `apiKey` / `modelName` / `thinkingEnabled`。
- 用户覆盖输入持久化到 `localStorage`，命名空间 `wolven_hunt.lobby.model_config.{slot}`，value 为 JSON `{baseUrl, apiKey, modelName, thinkingEnabled}`；不存在 key 时使用仓库默认配置显示。
- 读取旧版 `{baseUrl, apiKey, modelName}` 缓存时必须兼容：`thinkingEnabled` 缺失或不是 boolean 时回退对应 slot 的默认值。
- 写入采用 300ms debounce；读 / 写失败仅 `console.warn`，不阻塞 UI。
- 第一阶段大厅页**不读出**这些字段进任何 fetch / WebSocket / SSE；模型条目仅作为 UI 占位。P2 FastAPI 接入时由后端读取并通过 spectator 视角脱敏（与 §18.1 不绕过 Referee 的硬约束一致）。
- API key 在前端源码默认值与 `localStorage` 用户覆盖值中均为明文；`<input type="password">` 仅是视觉掩码，不提供加密保护，文档中需提示风险。

### 18.11 弹窗内 CTA Stubs

- StartModal 含「进入游戏」CTA 按钮：第一阶段 `console.log('[lobby] enter game')` + 关闭弹窗（已在 STEP-02 落地）；STEP-03 改为通过 `onEnterGame` prop 上报 App 层，由 App 触发 `lobby → game` 页面切换 + 过渡动画。
- HistoryModal 仅展示「功能开发中」占位文案，不放任何 CTA。
- SettingsModal 不含 CTA：所有改动通过受控输入实时 / debounce 写 `localStorage`，无「保存」按钮。

### 18.12 游戏准备页（Game Preparation Page）

- `App.tsx` 顶层维护 `page: 'lobby' | 'game'` 与 `phase: 'idle' | 'fade-out' | 'fade-in'` 两个 state；不引入路由库，避免增加依赖（与 §18.1 极小依赖原则一致）。
- 进入游戏过渡时序：`fade-out` 600ms ease-in（overlay 0→1，画面渐黑）→ `setPage('game')` 切换组件树 → 下一帧（`requestAnimationFrame`）切到 `fade-in` 800ms ease-out（overlay 1→0，白天背景渐亮）→ `idle`。
- 过渡 overlay 是固定挂在 `App.tsx` 的 `<div className="page-transition-overlay">`，z-index 9999，`pointer-events` 在 `fade-out` 阶段为 `all`（防止过渡中重复点击触发），其他阶段为 `none`。
- 进入游戏触发时同步调用 `useLobbyAudio.toggleMute()` 静音 BGM（仅当未 muted）；audio store 是模块级单例，lobby 卸载后 mute 状态保留。不新增 fadeOut ramp API；如需平滑淡出留给后续步骤。
- 游戏准备页 `<GamePage />`：白天背景图（`/assets/game/day_bg.png`）`object-fit: cover` 全屏；席位区分左右两列，每列 4 个席位垂直 flex 居中分布。
- 席位组件 `<GameSeat />` 两态：
  - 空态：圆形虚线边框 + lucide `Plus` 图标；点击触发 `ModelPicker` 弹窗。
  - 已分配态：圆形模型头像 + 外侧加粗昵称文字；点击头像同样触发 picker，可重新选择。昵称需带增强文字阴影，避免白天背景下可读性不足。
- 席位编号是 `<GameSeat />` 的纯 UI 徽标：基于 `seatIndex + 1` 显示 1–8，左列编号位于圆圈左下角，右列编号位于圆圈右下角；编号不写入 `assignments`，也不进入 Referee / FSM / RuleEngine 边界。
- 模型选择 `<ModelPicker />`：使用游戏页自有弹窗外壳（不复用大厅 `LobbyModal` 或 `settings_panel_bg.png`），渲染 `MODEL_SLOTS` 8 张卡片网格；已被其他席位占用的卡片主体 `disabled` + 灰度滤镜，但卡片右下角保留图标型「交换」按钮，用于把当前席位模型与该模型所在席位互换。当前席位已选卡片黄色边框高亮。
- 分配状态 `assignments: (number | null)[]`（长度 8）保存在 `<GamePage />` 内部 state；不写 `localStorage`，刷新页面恢复初态。每个 model slot 在 8 席位中至多出现一次。
- 模型交换只调换 `assignments` 中两个 seat index 的 slot 值，不写 `localStorage` / 事件日志 / replay，不触发 Referee / FSM / RuleEngine，也不清空按 model slot 记录的 `testResults`；测试徽标随模型头像移动。
- 「一键分配」是游戏准备页的纯 UI 快捷操作：入口位于左下角，由 `quick_assign_raccoon.png` 装饰图与按钮组成；点击后用 Fisher-Yates 洗牌 `MODEL_SLOTS` 的 0–7 索引并一次性写入 `assignments`。该随机不写事件日志、不参与 replay、不进入 Referee / FSM / RuleEngine；触发后必须清空旧 `testResults` 与测试提示，避免旧连通性标记误用于新席位。
- 席位身份占位 `.game-seat-role` 本步骤 `display: none`，作为 `身份分配 / 标识展示` 的扩展点，**不进入** Referee 边界；后续与游戏阶段同步显示分配结果时仍由 Referee 提供脱敏视角，不绕过 §18.1 单一权限边界。
- 游戏准备页**不发起任何网络请求**、**不引入游戏逻辑**、**不读取 `wolven_hunt/*` 模块**，与 §18.1 / §18.7 / §18.9 同等边界一致。
- 游戏准备页复用 `MODEL_SLOTS` 头像与昵称；模型 API 默认值只用于系统设置弹窗预填，不在本步骤用于席位分配或网络调用。

### 18.13 游戏内 UI 增强（Game Page Enhancements）

本节是 STEP-04 的架构契约，与 `plan.md` §14.14 一致。在 §18.12 基础上叠加：

- **`App.tsx` 双向页面切换**：新增 `targetPageRef: useRef<Page | null>` 记录 fade-out 后的目标页；`handleEnterGame` 设 `targetPageRef.current = 'game'` + `phase = 'fade-out'`，`handleExitGame` 设 `targetPageRef.current = 'lobby'` + `phase = 'fade-out'`。`onTransitionEnd` 在 fade-out 结束时读 `targetPageRef.current` 切页面 + 下一帧切 fade-in。退出时不自动还原 BGM 静音。
- **GamePage 内部 stage 状态机**：`stage: { dayNumber, phase }` 与 `bgPhase: 'idle' | 'fade-out' | 'fade-in'` 由 GamePage 持有；`pendingStageRef` 临时记录待切换的 stage。`<img class="game-bg" src={...}>` src 由 `stage.phase` 派生。`.game-stage-overlay` 的 z-index = 4，覆盖背景图但低于顶栏（z=5）和模态弹窗（createPortal 到 body）。**不复用** App 层 `.page-transition-overlay`，避免白天↔黑夜与 lobby↔game 切换互相耦合。
- **阶段与布局修正**：`StageIndicator` 显示太阳/月亮 + `第{dayNumber}天`，图标与文案垂直居中。席位昵称显示在头像下方并限制宽度；聊天区位于两列席位之间（当前 `left/right: clamp(118px, 25vw, 220px)`），底部预留操作区空间（当前 `bottom: clamp(200px, 20vh, 260px)`），在约 500px 宽 in-app browser 下也不得与昵称或底部按钮重叠。
- **GameTopBar / StageIndicator / GameChat / GameBottomActions / RulesModal / ExitConfirmModal** 全部位于 `src/components/Game/` 命名空间。`RulesModal` 使用游戏页自有弹窗外壳与滚动正文背景，不复用大厅 `settings_panel_bg.png`，并对 `rules.md` 做轻量 markdown 解析（标题 / 列表 / 加粗）后渲染为结构化正文；`ExitConfirmModal` 使用游戏页自有紧凑确认面板，不复用大厅竖版背景图；游戏页跨命名空间复用仅限通用 UI 外壳与 `MODEL_SLOTS` 静态配置。
- **席位测试态边界**：`<GameSeat testStatus>` 仅是 UI hint，不进入 Referee / FSM / RuleEngine；testStatus 由 GamePage 派生自 `testResults[assignment]`。`readModelConfig(slot)` 优先读取 `localStorage` 用户覆盖；没有用户覆盖时使用 `MODEL_CONFIG_DEFAULTS[slot]`，仅当有效 `baseUrl` / `apiKey` / `modelName` 缺失时返回 `null`，并兼容旧缓存的 `thinkingEnabled` 默认回退。`testResults` 与测试状态提示不写 `localStorage`，刷新或退出大厅再进入即重置。改 assignments 时清除被覆盖 slot 的 testResult。测试中按钮文案显示为「正在测试中」，并至少展示一次可感知的 loading 态；测试完成后每个已分配 slot 必须落成 `pass` 或 `fail`，底部显示通过数量摘要。
- **网络请求边界（§18.1 / §18.7 豁免登记）**：STEP-04 首次允许前端代码出现 `fetch()`，仅在以下两类受限场景：
  - **同源静态资源 fetch**（`/assets/game/rules.md`）：等价于 `<img>` / `<video>` 的资源加载，不构成跨域 / 后端 / LLM 调用，不破坏单一权限边界。
  - **用户主动触发的 LLM 配置自检 fetch**（`testModelConnection`）：仅响应"测试模型连通性"按钮点击；OpenAI 兼容协议，基础 body 为 `{model, messages, max_tokens: 1}`。若该 slot `thinkingEnabled === true`，请求体按模型名追加思考模式字段：`qwen*` 用 `enable_thinking: true`；`kimi*` / `mimo*` / `deepseek*` / `glm*` / `doubao*` 用 `thinking: {type: "enabled"}`；`hy3*` 用 `chat_template_kwargs: {thinking: true, reasoning_effort: "medium"}`；`MiniMax*` 用 `reasoning_effort: "medium"`。若 `thinkingEnabled === false`，不发送任何 thinking / reasoning 附加字段。返回值仅用于 ✓/✗ 视觉反馈，**不构成 PlayerView**、**不进事件日志**、**不参与胜负判定**。属于工具型调用，与 §18.1 "Referee 唯一权限边界"不冲突——因为它不产生任何游戏状态。
  - 这两类豁免**不允许**扩展到对局推进、聊天消息收发、玩家行动同步等任何 runtime 数据流；引擎数据流必须等 P2 接入 FastAPI 后由 Referee 控制。
  - apiKey 在 fetch header 明文传输；文档明确要求仅在 HTTPS 或本地 dev 使用。CORS 失败由用户感知为 ✗，不静默吞错。
  - **未来规划**：P2 接入 FastAPI 后，连通性测试改走后端 `POST /api/test-model`，前端只发同域请求；STEP-04 直连是过渡方案。届时 §18.13 本节豁免 B 收紧。
- **DEV-only 调试入口**：`import.meta.env.DEV` 守卫的 [debug] 推进按钮仅供开发期预览白天/黑夜切换；生产 Vite 构建会 tree-shake；不进入交付路径。
