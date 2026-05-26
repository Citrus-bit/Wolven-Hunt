# STEP-07 / P3 — 观赛 MVP（真实 LLM × 叙事化事件流 × 节奏 × 角色揭晓）

本文档是 STEP-07 的执行手册与验收指标。GPT 实施时必须以本文为准；与 `plan.md` / `architecture.md` 冲突时，先更新 `plan.md` 再同步代码（参见仓库根 AGENTS.md 硬约束）。

## 0. 目标

STEP-06 已经把后端引擎 + LLM 网关 + SSE + replay 打通。STEP-07 的目标是：**让用户从前端「开始游戏」到一局结束，能以观众视角完整看完一场实战 AI 狼人杀**，并且符合 `狼人杀需求阐明.md` §二 / §三 中关于音视频、倒计时、状态显示、女巫夜晚行动状态、高亮特效的全部要求。包括：

1. **真实 LLM 入场**：前端 `assignments` 把每个座位绑定到一个 model slot；后端按 per-seat 路由调用对应 provider；CI 仍走 mock，真模型由 env 显式开启。
2. **叙事化事件流**：把当前 raw JSON 事件渲染成「中文叙事 + 角色头像 + 阶段标记」；观众页使用上帝视角，座位头像显示身份徽标，狼聊面板展示真实狼人夜聊；raw response 和 provider 配置仍不得进入前端。
3. **节奏控制**：可配置的 phase / speech 间隔，让前端有时间渲染、用户有时间阅读；CI / replay 走 0 延迟模式不变慢。节奏必须与音频时长对齐（见 §A 音视频契约）。
4. **观赛 UI 改造**：进入夜晚后清空 "夜深了... / 一键分配 / 测试连通性 / 绿色对勾"，聊天框上方改为「倒计时 + 状态显示」；玩家发言时座位高亮特效；女巫夜晚行动状态展示；投票直方图。
5. **音频接入**：把素材目录的 9 条游戏 mp3 按需求文档 §二/§三 的脚本播放；女巫不使用专属视频，BGM 在游戏内淡入淡出与大厅切换。
6. **结局揭晓**：`game_end` 后追加 `role_reveal` 公开事件 + 前端结局浮层（胜方 / 全员身份 / 关键事件回顾）。
7. **NotebookOps**：`runs/{game_id}/` 写入 `narrative.jsonl`（叙事行）和 `final_reveal.json`，便于 STEP-08 历史回放复用。
8. **观赛特效流**：后端从完整 EventLog 派生 `spectator_effect`，前端展示护盾、狼袭、预言、女巫药瓶和死亡揭晓动画；普通 PlayerView、prompt、raw spectator events 仍不暴露私有事件原文。

**不在本步骤范围**（留给 STEP-08）：property test 扩展、千局公平性回归、token 预算实测、人类入座 per-seat SSE、历史回放 UI、prompt A/B。

## 1. plan.md / architecture.md 同步清单

实施前先把以下内容写进 `plan.md` 和 `architecture.md`，再写代码：

### 1.1 plan.md

- §3.3 事件枚举：新增 `role_reveal`（公开）、`pacing_tick`（公开，仅记录节奏锚点，可选）。
- §5.4 落盘目录：在 `runs/{game_id}/` 增加 `narrative.jsonl`、`final_reveal.json`。
- §9.1 环境变量：新增 `WH_PACING_PROFILE`（`live | fast | off`，默认 `live`）、`WH_PACING_PHASE_MS`、`WH_PACING_SPEECH_MS`、`WH_PACING_NIGHT_MS`、`WH_LLM_PROVIDER_MAP`（空字符串或路径，指向 per-seat provider map）。
- §11 路线图：标记 STEP-07 为「P3 观赛 MVP（不是工程化）」，工程化拆到 STEP-08。
- 当前阶段提示更新为 `STEP-07 / P3 观赛 MVP`。

### 1.2 architecture.md

- §9 事件目录：登记 `role_reveal` schema（`payload: { winner, seats: [{seat, role, alive}] }`，仅在 `GAME_END` 后由 Referee 生成，公开可见）。
- §12 Provider 路由：新增 per-seat provider map 契约：`ProviderMap = dict[seat_number, ProviderConfig]`，未指定座位回退到全局 `WH_LLM_*`。
- §13 节奏：新增节奏控制器契约（`PacingController`，由 FSM 在 `state_sink` 钩子中调用；`pacing.profile=off` 时为零开销 no-op）。
- §15 环境变量：镜像 §9.1 新增项。

硬约束保持不变：

- Referee 仍是唯一权限边界。`role_reveal` 由 Referee 在 `GAME_END` 之后生成，**不得**绕过事件日志。
- 节奏控制只在「现场观赛」语义下生效；replay / property test / CI 必须强制 `pacing.profile=off`。
- per-seat provider map **只决定调用哪个模型**；不绕过 PlayerView，不下发私有信息到前端。

## 2. Python 工程链

### 2.1 新增文件

```
src/wolven_hunt/llm/provider_map.py        # ProviderMap + 路由器
src/wolven_hunt/orchestration/pacing.py    # PacingController
src/wolven_hunt/storage/narrative.py       # 事件 → 叙事行（中文模板）
src/wolven_hunt/referee/reveal.py          # role_reveal 生成器
configs/games/_provider_maps/               # 默认 provider map 模板（可空）
  └── classic_8.example.yaml
tests/unit/test_pacing.py
tests/unit/test_provider_map.py
tests/unit/test_role_reveal.py
tests/unit/test_narrative.py
tests/integration/test_spectator_mvp.py
```

### 2.2 修改文件

- `src/wolven_hunt/config/settings.py`：新增 §1.1 列出的所有 `WH_PACING_*` 与 `WH_LLM_PROVIDER_MAP`；保留 strict validation。
- `src/wolven_hunt/llm/provider.py`：保留 `MockLLMProvider` / `LiteLLMProvider` / `ReplayLLMProvider`；新增 `build_provider_for_seat(seat, provider_map, settings)` 工厂。
- `src/wolven_hunt/orchestration/runtime.py`：
  - `GameRegistry._build_agents` 改用 ProviderMap 路由；
  - `_run_game` 注入 `PacingController`，把它的 `before_phase / after_speech / before_night` 钩子接到 `state_sink` / `control_hook`。
  - `CreateGameRequest.agents` 语义升级：保留旧的 `dict[seat, str]`（`mock` / `llm:slot=N`），新增 `dict[seat, {provider, model, base_url, api_key_env}]` 兼容写法。spec 的字段名要在 §3 锁死。
- `src/wolven_hunt/storage/disk.py`：新增 `append_narrative(row)` / `write_final_reveal(payload)`；fsync 与现有 jsonl sink 一致。
- `src/wolven_hunt/orchestration/fsm.py`：在 `emit_win_check` 走完 + `state.winner is not None` 时，调用 `referee.reveal.build_role_reveal(state)` 写入 `EventLog`。
- `src/wolven_hunt/api/routes_games.py`：
  - 新增 `GET /games/{id}/narrative` 返回 `tuple[narrative_row, ...]`（spectator-safe）；
  - 新增 `GET /games/{id}/reveal` 返回 `final_reveal.json`（仅在 `winner != null` 时返回 200，否则 404 `code=game_not_finished`）；
  - `POST /games` 接受新版 `agents` schema；老 schema 仍然兼容。
- `src/wolven_hunt/api/schemas.py`：
  - `AgentSpec = AgentSpecMock | AgentSpecLLM`（`Discriminator` on `kind`）；`CreateGameRequest.agents: dict[int, AgentSpec]`。
  - `RoleRevealResponse`、`NarrativeRow`。
- `src/wolven_hunt/storage/replay.py`：`replay_resimulate` 必须在 `pacing.profile=off` 下运行，断言无 `pacing_tick` 影响事件 hash。
- `src/wolven_hunt/api/cli.py`（如果存在 `serve` / `resimulate`）：新增 `--pacing live|fast|off`，默认 `serve` 用 `live`，`resimulate` 强制 `off`。

### 2.3 ProviderMap 契约

```python
# src/wolven_hunt/llm/provider_map.py
@dataclass(frozen=True, slots=True)
class ProviderConfig:
    provider: Literal["mock", "litellm"]
    model: str
    base_url: str = ""
    api_key: str = ""  # 解析后的明文，运行内存中持有；不写盘
    timeout_seconds: float = 30.0

class ProviderMap:
    def __init__(self, *, default: ProviderConfig, per_seat: Mapping[int, ProviderConfig]) -> None: ...
    def for_seat(self, seat: Seat) -> ProviderConfig: ...
```

- `WH_LLM_PROVIDER_MAP` 为空 → 全部走全局 `WH_LLM_*`。
- 非空 → 解析 YAML（`configs/games/_provider_maps/*.yaml`），缺失座位回退到全局。
- API key 来源优先级：`agents` 入参 > yaml 中 `api_key_env` 解出的 env > 全局 `WH_LLM_API_KEY`。
- ProviderConfig **不进事件日志、不进 narrative、不进 spectator 视图**；仅在内存中持有。

### 2.4 PacingController 契约

```python
# src/wolven_hunt/orchestration/pacing.py
@dataclass(frozen=True, slots=True)
class PacingProfile:
    name: Literal["live", "fast", "off"]
    phase_ms: int        # phase 切换间隔（默认 live=600, fast=80, off=0）
    speech_ms: int       # 每条 speech / wolf_chat / last_words 之后
    night_ms: int        # 进入 NIGHT_* 阶段额外停顿

class PacingController:
    def __init__(self, profile: PacingProfile, *, sleeper: Callable[[float], None] = time.sleep) -> None: ...
    def on_state(self, state: GameState) -> None: ...   # 接到 state_sink，按 phase 切换决定停顿
```

- `profile=off` 时所有方法是 no-op，开销 = 一次属性读。
- `sleeper` 可注入 mock，单测必须用 mock sleeper 验证调用次数与累计时长。
- live profile **不引入** event；不写 `pacing_tick` 进事件日志（避免污染 replay hash）。如果未来需要客户端端节奏锚点，再走 §1.1 的 `pacing_tick`，但 STEP-07 暂不实现。

### 2.5 Role Reveal 契约

```python
# src/wolven_hunt/referee/reveal.py
def build_role_reveal(state: GameState) -> Event:
    # type=role_reveal, visibility=public, payload={
    #   "winner": "wolves" | "good",
    #   "seats": [{"seat": 1, "role": "wolf", "alive": false}, ...],
    #   "highlights": [{"seq": int, "summary": str}, ...],  # 关键事件回顾，3-5 条
    # }
```

- 仅在 `state.winner is not None` 时调用；幂等（多次调用产生同一 event_id，因为基于 deterministic 序列号）。
- highlights 选取规则：第一夜死亡、女巫用药命中/失误、首次预言家结果（仅 seer 可见的 raw 事件，但 reveal 阶段公开）、放逐结果。固定模板，**不**走 LLM。

### 2.6 Narrative 契约

```python
# src/wolven_hunt/storage/narrative.py
@dataclass(frozen=True, slots=True)
class NarrativeRow:
    seq: int
    day: int
    phase: str
    kind: Literal["system", "speech", "action", "announce", "verdict"]
    text: str          # 中文叙事，单行
    actor: int | None
    icon: str | None   # 可选，对应 model_icon 或 system 图标
```

- 输入：spectator 视角的 `Event`。
- 输出：每个 spectator 可见 event 一行。例：
  - `phase_enter NIGHT_GUARD` → `{kind:"system", text:"夜幕降临，守卫开始行动"}`
  - `speech` → `{kind:"speech", actor:3, text:"3号：我是村民..."}`
  - `vote_cast` → `{kind:"action", text:"5号投票给2号"}`
  - `vote_result` → `{kind:"verdict", text:"投票结果：2号 4票 / 5号 2票"}`
  - `role_reveal` → 不入 narrative，单独走 final_reveal。
- 文案模板写在 `src/wolven_hunt/storage/narrative.py` 内的常量字典；首版纯模板，不走 LLM。

## 3. API 表面（FastAPI）

### 3.1 升级 `POST /games`

```jsonc
{
  "config_path": "configs/games/classic_10.yaml",
  "seed": "web-1737000000",
  "agents": {
    "1": {"kind": "mock"},
    "2": {"kind": "llm", "provider": "litellm", "model": "openai/gpt-4o-mini",
           "base_url": "https://api.openai.com/v1",
           "api_key_env": "OPENAI_API_KEY"},
    "3": {"kind": "llm", "provider": "litellm", "model": "qwen/qwen3-plus",
           "base_url": "https://...", "api_key": "sk-..."}
  },
  "pacing": "live"   // 可选，覆盖 WH_PACING_PROFILE
}
```

- `agents` 缺省条目 → 走 `WH_LLM_PROVIDER_MAP` / 全局；完全为空 → 全部 mock。
- `api_key` 直传仅推荐前端临时 demo 用；正式部署应该用 `api_key_env` 让后端从 env 读。
- 后端**不**回显 api_key（`GameSummaryResponse` 不含）。
- 老 schema `dict[int, str]`（`"mock"` / `"llm"`）保留兼容；解析时若是 str 走旧分支。

### 3.2 新增 `GET /games/{id}/narrative`

- 返回 `tuple[NarrativeRow, ...]`，spectator-safe（基于 Referee 过滤后的 spectator events 渲染；普通叙事不包含 raw response/provider 配置）。
- 支持 `?after=<seq>` 增量拉取（用于前端在 SSE 重连后回放叙事）。

### 3.3 新增 `GET /games/{id}/reveal`

- `winner is None` → 404 `{code: "game_not_finished"}`。
- 否则返回 `final_reveal.json` 内容。
- spectator-safe；不返回 raw_response 引用。

### 3.4 SSE 事件类型扩展

- 现有 `event: game_event` 不变（Referee 过滤后的 spectator Event；STEP-07 观众上帝视角包含身份表和狼人夜聊）。
- 新增 `event: narrative_row`（增量推送 NarrativeRow）。前端可二选一消费。
- `event: heartbeat` 不变。
- `Last-Event-ID` 行为不变；`narrative_row` 与 `game_event` 共享 seq 序列（同源 event）。

## 4. 前端（src/components/Game/）

### 4.1 StartModal → GamePage 数据流升级

现状：

- StartModal 里 `createGame()` 不带 agents，进入 GamePage 后 `assignments` 是前端独立 state，**没传给后端**。

升级：

- 让用户先在 GamePage 完成「席位分配 + 连通性测试」，然后点「进入夜晚」时**重新调用** `POST /games` 传 agents（或新增 `POST /games/{id}/configure_agents`，但首选前者：丢弃前面创建的空 game，重建一个绑定真实 agent specs 的 game）。
- StartModal 的「进入游戏」CTA 改为：不立刻 `createGame`，只 `onEnterGame(null)`；GamePage 在 `assignments` 全部 pass 测试后，点「进入夜晚」才调用 `createGame(agents)`。
- `gameApi.ts` `createGame` 新签名：
  ```ts
  type AgentSpec =
    | { kind: 'mock' }
    | { kind: 'llm'; provider: 'litellm'; model: string; base_url: string; api_key: string };
  export async function createGame(opts: {
    seed?: string;
    agents?: Record<number, AgentSpec>;
    pacing?: 'live' | 'fast' | 'off';
  }): Promise<CreateGameResponse>;
  ```
- GamePage 在「进入夜晚」时把 `assignments` 转成 `Record<seatNumber, AgentSpec>`：从 `MODEL_CONFIG_DEFAULTS[slot]` 读 baseUrl/apiKey/modelName，组成 `{kind:"llm", provider:"litellm", model, base_url, api_key}`。

### 4.2 GameChat → 叙事化

- `GameChat` 改造：消费 `narrative_row` 事件（或前端用 `formatEvent` 升级版从 raw events 派生）。第一版**优先**走前端派生（无需改 SSE），减少耦合。
- 新增 `src/lib/narrative.ts`：纯前端函数 `toNarrative(event: GameEvent): NarrativeRow | null`，与后端 `narrative.py` 模板**保持一致**。锁定一个 fixture 文件 `tests/frontend/narrative.fixture.json`，前后端各自一组单测验证：同一 event 输入产出**完全相同**的中文文本。
- 渲染：
  - `system` → 灰色斜体居中。
  - `speech` → 左侧 model 头像（来自 `assignments[actor-1]` → `MODEL_SLOTS[slot].iconPath`）+ 玩家昵称 + 发言气泡。
  - `action` → 单行小字。
  - `announce` / `verdict` → 加粗。
- 移除 GamePage 里的 `setInterval(refresh, 1000)`（SSE 已经覆盖）；只在 SSE `error` 时手动 refetch 一次 `getGame`。

### 4.3 角色揭晓浮层

- 新增 `src/components/Game/FinalRevealOverlay.tsx`：当事件流出现 `role_reveal` 或 `streamStatus` 终止后 fetch `/games/{id}/reveal`，渲染：
  - 顶部 banner：`狼人胜利` / `好人胜利`。
  - 10 个座位卡片：头像 + 昵称 + 真实身份 + 存活状态。
  - 关键事件回顾（来自 `highlights`）。
  - CTA：「再来一局」（`onExitGame()` 后回大厅）/「查看完整事件」（toggle `GameChat` 显示原始 JSON）。
- 浮层在游戏未结束时不渲染；结束时盖在 `GamePage` 之上。

### 4.4 节奏感（前端协同）

- 后端 `live` profile 已经在事件之间 sleep；前端只需在 `narrative_row` push 时做轻量 fade-in 动画（CSS `opacity 0→1, 200ms`）。
- 不在前端做额外 `setTimeout` buffer，避免与后端节奏叠加。

### 4.5 stage 切换修正

- 现在 `GamePage` 用最后一条 event 的 phase 推 stage；新版改用 `phase_enter` 事件中第一条 `NIGHT_*` / `DAY_*` 标志位推 stage，避免 `NIGHT_WITCH` 这种瞬时 phase 把白天误判成夜晚。

## 5. 实施顺序（建议）

1. **plan.md / architecture.md 同步**（§1）。
2. **配置 + Provider Map**：`Settings` 扩展 + `provider_map.py` + 单测。
3. **PacingController**：实现 + 单测 + 接入 `runtime.py`。
4. **Role Reveal + Narrative**：`reveal.py` / `narrative.py` + 单测。
5. **API**：`schemas.py` 升级 + `routes_games.py` 三个端点（含 `POST /games/{id}/ack`）+ `GameSummaryResponse.timings` + 集成测试。
6. **CLI**：`serve` / `resimulate` 加 `--pacing`，replay 强制 `off`。
7. **前端**：`copy:game-audio` 脚本 → `gameAudio.ts` / `audioAssets.ts` → `phaseDescriptor.ts` + `GamePhaseHeader`（倒计时 + 状态）→ `gameApi.ts` 签名升级 → `narrative.ts` → GamePage 数据流改造（隐藏准备态按钮、对接 ack） → GameChat 叙事化 + `VoteHistogram` → 女巫阶段状态 → `FinalRevealOverlay`。
8. **手动 smoke**：`WH_LLM_PROVIDER=litellm` 跑一局真实 LLM 实战，从前端开始游戏到 reveal 浮层全流程；截图三张（开局、白天发言、结局浮层）入 `docs/specs/step-07-screenshot-*.png`。

## 6. 验收指标（GPT 必须全部满足）

### A. plan/architecture 同步
- `rg "role_reveal" plan.md architecture.md` 两文件都命中。
- `rg "WH_PACING_" plan.md architecture.md .env.example` 全部命中。
- `plan.md` 当前阶段标记从 STEP-06 改为 STEP-07。

### B. ProviderMap
- `tests/unit/test_provider_map.py` 覆盖：空 map 全局回退、部分 map 部分回退、`api_key_env` 解析失败抛错、`api_key` 不写盘（断言 `runs/{id}/manifest.json` 不含 key）。
- mypy strict 0 errors。

### C. Pacing
- `tests/unit/test_pacing.py` 覆盖：`profile=off` 0 调用、`live` profile 在 100 条事件下累计 sleep ≥ `phase_ms * 阶段切换数`、`fast` profile 不超过 `live` 的 1/4。
- `replay_resimulate` 在 `live` 配置下产出的事件序列与 `off` 完全相同（hash 比较）。

### D. Role Reveal
- `tests/unit/test_role_reveal.py` 覆盖：`winner=None` 时不生成、`winner=wolves` 时 10 座位身份完整、highlights 长度 ∈ [3, 5]。
- 集成测试断言 `events[-1].type == "role_reveal"`。

### E. Narrative
- `tests/unit/test_narrative.py` 覆盖前端 fixture 中的 12 类事件 → 中文文案逐字匹配。
- 前后端共用同一份 fixture（`tests/fixtures/narrative_cases.json`）。

### F. API
- `POST /games` 接受新 schema、老 schema 都通过；schema 校验失败返回 422 `code=invalid_agent_spec`。
- `GET /games/{id}/narrative` 在游戏进行中可增量拉取；`?after=` 行为正确。
- `GET /games/{id}/effects` 在游戏进行中可增量拉取；`?after=` 行为正确，并可从离线 `events.jsonl` 重建。
- `GET /games/{id}/reveal` 在 winner=None 时 404，结束后 200。
- `tests/integration/test_spectator_mvp.py`：mock provider 跑完整局，断言 SSE 收到 ≥1 条 `narrative_row` 与 ≥1 条 `spectator_effect`、最终 `role_reveal` 出现、`/reveal` 200。

### G. 前端
- `npm run typecheck` + `npm run lint` 全绿。
- `npm run build` 成功。
- `tests/frontend/narrative.test.ts`（vitest 或现有测试栈）覆盖 `toNarrative` 至少 12 用例。
- 手动 smoke 截图入 `docs/specs/`。

### H. 整体质量门
- `uv run ruff check src tests` 0 错。
- `uv run ruff format --check src tests` 0 错。
- `uv run mypy --strict src` 0 错。
- `uv run pytest` 全绿，`-q` 输出测试数比 STEP-06 验收时（53）至少多 12。
- CI 默认仍走 mock；不引入任何默认联网/默认消耗 API key 的测试。

### I. 用户可达成的端到端体验
- 用户在 `npm run dev` + `uvicorn` 起的环境下：
  1. 大厅点开始游戏。
  2. GamePage 选好 10 个 model（一键分配可用）。
  3. 点测试，全部 pass。
  4. 点进入夜晚，后端开始真实 LLM 跑局。
  5. 通用聊天框按节奏滚动出中文叙事 + 头像；NIGHT/DAY 背景自动切换。
  6. 一局结束（≤ 5 分钟，10 模型同时调用），FinalRevealOverlay 弹出，展示胜方 + 10 座位身份 + 关键回顾。
  7. 点再来一局回大厅。

## 7. 风险登记

| 风险 | 缓解 |
|---|---|
| 真实 LLM 8 路并发可能超预算或超时 | `WH_LLM_BUDGET_PER_GAME` 已存在；超预算事件 `agent_budget_warning` 会公开提示；timeout 走 fallback。 |
| 不同 provider 输出格式差异导致结构化校验失败率高 | 仍走 STEP-06 的重试 + fallback；本步骤不改重试策略。 |
| 节奏控制让 SSE 客户端等太久 → heartbeat 30s 已经能保活，但用户感觉卡 | `live` profile 默认 `phase_ms=600`、`speech_ms=400`，一整局 ~3-5 分钟。可通过 `?pacing=fast` 切换。 |
| 前后端 narrative 模板漂移 | 共用 fixture，CI 强制比对。 |
| ProviderConfig.api_key 泄漏到事件日志或前端 | ProviderConfig 仅在内存；`event_payload()` 已不带 raw_response；新增 ProviderMap 时单测断言 manifest / events / spectator 都不含 key。 |

## 8. 验证方法（一键脚本）

```bash
# 离线 / mock
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy --strict src
uv run pytest -q
npm run typecheck && npm run lint && npm run build

# 真实 LLM smoke（手动，不入 CI）
WH_LLM_PROVIDER=litellm \
WH_LLM_MODEL=openai/gpt-4o-mini \
WH_LLM_API_KEY=$OPENAI_API_KEY \
uv run uvicorn wolven_hunt.api.app:app --reload &
npm run dev
# 浏览器跑一局，截图 3 张存入 docs/specs/。
```

## A. 音视频 + 倒计时 + 状态显示 + 女巫行动（对齐 `狼人杀需求阐明.md` §二/§三）

本节是 STEP-07 的硬需求来源之一。**实施前必须先阅读** `狼人杀需求阐明.md` §二「游戏流程」与 §三「特殊注意事项」。

### A.1 素材清单与搬运

源文件位于仓库根 `素材/`，**不得重命名、移动或删除**该目录（仓库根 AGENTS.md 硬约束）。STEP-07 通过新增脚本 `scripts/copy_game_audio.mjs`（参照 STEP-01b 的 ffmpeg 搬运脚本思路）把以下文件**复制**到 `public/assets/game/` 并改成 ASCII 文件名，供前端按相对路径加载：

| 源（素材/） | 目标（public/assets/game/） | 用途 |
|---|---|---|
| `狼嚎.mp3` | `audio/wolf_howl.mp3` | 入夜开场，先播 |
| `天黑了，守卫请睁眼.mp3` | `audio/night_guard.mp3` | 接 `wolf_howl` 后播 |
| `狼人请睁眼.mp3` | `audio/night_wolves.mp3` | 守卫结束后播 |
| `预言家请睁眼.mp3` | `audio/night_seer.mp3` | 狼人投票结束后播 |
| `鸡鸣.mp3` | `audio/day_rooster.mp3` | 天亮第一段 |
| `天,亮了.mp3` | `audio/day_dawn.mp3` | 接 `day_rooster` 后播 |
| `昨晚,他死了.mp3` | `audio/day_death.mp3` | 当 `DAY_ANNOUNCE` 有死亡时播 |
| `昨晚,是平安夜.mp3` | `audio/day_peaceful.mp3` | 当 `DAY_ANNOUNCE` 无死亡时播 |
| 无女巫视频素材 | 不使用 | 女巫只显示阶段状态 |
| `游戏大厅待机音乐.mp3` | `audio/lobby_bgm.mp3`（已在 `public/assets/lobby/lobby_bgm.mp3` 存在则跳过） | BGM |

脚本要求：
- 可重入（已存在且 hash 一致则跳过）。
- 在 `package.json` 加 `"copy:game-audio": "node scripts/copy_game_audio.mjs"`，并在 `predev` / `prebuild` 钩子里串接。
- 输出清单写入 `public/assets/game/audio_manifest.json`（前端 `src/lib/audioAssets.ts` 直接 import 该 manifest 拿到 path + duration_ms（duration_ms 可由 `ffprobe` 在脚本中算出；ffprobe 缺失时降级为静态预设 ms，避免 CI 失败）。

### A.2 前端音视频播放契约

新增 `src/lib/gameAudio.ts`：
```ts
export type GameAudioKey =
  | 'wolf_howl' | 'night_guard' | 'night_wolves' | 'night_seer'
  | 'day_rooster' | 'day_dawn' | 'day_death' | 'day_peaceful';

export interface AudioController {
  play(key: GameAudioKey): Promise<void>;        // resolve 时表示已播完
  playSequence(keys: GameAudioKey[], gapMs: number): Promise<void>;
  stopAll(): void;
  setMuted(muted: boolean): void;
  setVolume(v0to1: number): void;
}
```
- 使用单例 `HTMLAudioElement` 池；同一 key 复用同一元素，重播时 `currentTime=0`。
- 音量从大厅 `SettingsModal` 的音量 slider 同步（`VOLUME_DEFAULT=80`）。
- 浏览器 autoplay 限制：在 LobbyHome → GamePage 切换之前用户必然有 click 交互，所以 GamePage mount 时 audio context 已可用；首次播放前若仍被拒，降级为「静音播放占位 + 提示用户解锁声音」按钮（不在 §6 验收范围内，写成 best-effort）。
- 女巫不使用视频覆盖层，`NIGHT_WITCH` 展示阶段状态与倒计时，并播放 `女巫请睁眼.mp3` 对应的 `night_witch` 音频。

### A.3 音频脚本（与后端节奏对齐）

严格按 `狼人杀需求阐明.md` §二 「第一天黑夜」/「第二天白天」的描述编排。前端在 SSE 事件抵达时按下表触发音频，并**让后端 PacingController 等到音频播完**（前端在播完后通过新接口 `POST /games/{id}/ack`（见 §A.5）告知后端解锁）：

| 触发事件 (SSE) | 前端动作 | 后端等待 |
|---|---|---|
| `phase_enter NIGHT_START` | 1s 停顿 → 播 `wolf_howl` → 播 `night_guard` | 等待 `ack:night_intro_done` |
| `phase_enter NIGHT_WOLF_CHAT` | 1s 停顿 → 播 `night_wolves` | 等待 `ack:night_wolves_done` |
| `phase_enter NIGHT_SEER` | 1s 停顿 → 播 `night_seer` | 等待 `ack:night_seer_done` |
| `phase_enter DAY_ANNOUNCE` | 播 `day_rooster` → 播 `day_dawn` → 若 `death_at_night` 存在则播 `day_death` 否则播 `day_peaceful` | 等待 `ack:day_intro_done` |
| `phase_enter NIGHT_WITCH` | 1s 停顿 → 播 `night_witch`，显示「女巫正在行动」状态与倒计时 | 等待 `ack:night_witch_done` |
| 其余 phase | 无音频 | 无需 ack |

### A.4 倒计时 + 状态显示（聊天框上方）

现 `GamePage` 进入夜晚时（首次出现 `phase_enter NIGHT_*`）：
- 隐藏：`夜深了...` 按钮、`一键分配`、`测试连通性`、`game-seat-badge`（绿色对勾）、`game-stage-debug`。
- 在 `GameChat` 上方挂接 `<GamePhaseHeader />`，包含：
  - 倒计时：从 `phase_enter` 时刻起按 §A.6 时长 countdown。
  - 状态显示：单行中文，例如「守卫正在行动」「狼人正在讨论」「狼人正在行动」「预言家正在行动」「N号玩家正在发言」「正在举行公民投票」「正在 PK 重投」「女巫用药中」。状态文案与 phase 的映射写在 `src/lib/phaseDescriptor.ts`，单元测试覆盖全部 phase。
- 行动状态位置：对话框上方、倒计时下方（对齐需求文档 §三.8）。

### A.5 ack 接口（前端 → 后端）

新增 `POST /games/{id}/ack`：
```jsonc
{ "phase": "NIGHT_START", "event": "night_intro_done", "client_event_id": "..." }
```
- 后端 `GameSession` 在 `PacingController` 中等待对应 ack 信号才继续推进；超时（默认 15s，由 `WH_PACING_ACK_TIMEOUT_MS` 配置）后自动 unblock，记录 hidden `agent_timeout` 事件以便 replay 复盘。
- ack 仅决定**节奏**，不影响 FSM 状态机或事件 hash；`pacing.profile=off` 时后端不等待 ack，前端也不发送。
- ack 不进事件日志（避免污染 replay）；只走内存事件信号。

### A.6 倒计时秒数（需求文档对齐）

| Phase | 倒计时 |
|---|---|
| `NIGHT_GUARD` | 60s（AI 选守护对象） |
| `NIGHT_WOLF_CHAT` | 120s（狼人轮流发言） |
| `NIGHT_WOLF_VOTE` | 30s |
| `NIGHT_SEER` | 60s |
| `DAY_SPEECH`（每位玩家） | 60s + 1s 间隔 |
| `DAY_VOTE` / `DAY_VOTE_PK` | 30s |
| `DAY_LAST_WORDS` | 60s |

这些秒数写入 `configs/games/_rule_sets/majority_or_side_elimination.yaml` 的 `timings` 段；前端从 `GET /games/{id}` 拿到 timings（新增 `GameSummaryResponse.timings`）显示倒计时，后端 PacingController 同源读取，保持单一事实源。

### A.7 高亮特效 / 投票直方图

- **发言高亮**：`GameSeat` 在自己是当前发言者时（`current_speaker_seat === seatIndex+1`）应用 `.game-seat--speaking` 类，CSS 添加 outline + glow + 1s pulse 动画。当前发言者由前端从 `speech` 事件 actor 字段维护（在该 phase 内最后一个 speech 的 actor 即当前发言者）。
- 女巫不新增视频组件；复用 `GamePhaseHeader` 展示 `NIGHT_WITCH` 状态并由音频 ack 对齐 pacing。
- **投票直方图**：在 `GameChat` 通用面板内，`vote_result` 事件触发渲染 `VoteHistogram`（横向条 + 票数）。在 `vote_pk_enter` 时清空，重投后再次渲染。

### A.8 plan.md / architecture.md 同步追加

除 §1 已列内容外，**还需**：

- `plan.md`：在 §1.8 / §1.7 / §3 流程中追加各 phase 的 `timings` 引用；在 §11 列出「STEP-07 引入前端音视频脚本 + ack 节奏接口」。
- `architecture.md`：新增「§16 节奏与音视频对齐」一节，描述 `PacingController` ↔ `ack` ↔ 前端 audio sequence 的握手协议；明确 ack 不进事件日志、不影响 replay hash。
- `.env.example` 追加 `WH_PACING_ACK_TIMEOUT_MS=15000`。

### A.9 测试与验收追加

在 §6 既有验收门基础上**叠加**以下硬指标：

- `tests/unit/test_phase_descriptor.py`（其实在前端 vitest 侧）覆盖所有 phase → 中文文案映射。
- `tests/unit/test_pacing_ack.py`：mock provider 跑一局，断言 `ack` timeout 时 PacingController 仍能推进。
- `tests/integration/test_audio_manifest.py`：断言 `public/assets/game/audio_manifest.json` 9 条游戏音频齐全，`public/assets/game/effect_manifest.json` 6 条图片特效齐全，hash 与素材原文件一致，且不包含视频条目。
- `npm run build` 必须先跑 `copy:game-audio`；CI 在没有 ffprobe 的环境下用预设 duration 也不能失败。
- 手动 smoke 截图新增 2 张：夜晚倒计时 + 女巫状态显示。
- 手动 smoke 录屏（可选，写入 `docs/specs/step-07-smoke.mp4`），证明：入夜音频序列正确、倒计时与状态显示正确、发言高亮、女巫状态显示、结局浮层。

## A. 音视频 + 倒计时 + 状态显示 + 女巫行动（对齐 `狼人杀需求阐明.md` §二/§三）

本节是 STEP-07 的硬需求来源之一。**实施前必须先阅读** `狼人杀需求阐明.md` §二「游戏流程」与 §三「特殊注意事项」。

### A.1 素材清单与搬运

源文件位于仓库根 `素材/`，**不得重命名、移动或删除**该目录（仓库根 AGENTS.md 硬约束）。STEP-07 通过新增脚本 `scripts/copy_game_audio.mjs`（参照 STEP-01b 的 ffmpeg 搬运脚本思路）把以下文件**复制**到 `public/assets/game/` 并改成 ASCII 文件名，供前端按相对路径加载：

| 源（素材/） | 目标（public/assets/game/） | 用途 |
|---|---|---|
| `狼嚎.mp3` | `audio/wolf_howl.mp3` | 入夜开场，先播 |
| `天黑了，守卫请睁眼.mp3` | `audio/night_guard.mp3` | 接 `wolf_howl` 后播 |
| `狼人请睁眼.mp3` | `audio/night_wolves.mp3` | 守卫结束后播 |
| `预言家请睁眼.mp3` | `audio/night_seer.mp3` | 狼人投票结束后播 |
| `鸡鸣.mp3` | `audio/day_rooster.mp3` | 天亮第一段 |
| `天,亮了.mp3` | `audio/day_dawn.mp3` | 接 `day_rooster` 后播 |
| `昨晚,他死了.mp3` | `audio/day_death.mp3` | 当 `DAY_ANNOUNCE` 有死亡时播 |
| `昨晚,是平安夜.mp3` | `audio/day_peaceful.mp3` | 当 `DAY_ANNOUNCE` 无死亡时播 |
| 无女巫视频素材 | 不使用 | 女巫只显示阶段状态 |
| `游戏大厅待机音乐.mp3` | `audio/lobby_bgm.mp3`（已在 `public/assets/lobby/lobby_bgm.mp3` 存在则跳过） | BGM |

脚本要求：
- 可重入（已存在且 hash 一致则跳过）。
- 在 `package.json` 加 `"copy:game-audio": "node scripts/copy_game_audio.mjs"`，并在 `predev` / `prebuild` 钩子里串接。
- 输出清单写入 `public/assets/game/audio_manifest.json`（前端 `src/lib/audioAssets.ts` 直接 import 该 manifest 拿到 path + duration_ms（duration_ms 可由 `ffprobe` 在脚本中算出；ffprobe 缺失时降级为静态预设 ms，避免 CI 失败）。

### A.2 前端音视频播放契约

新增 `src/lib/gameAudio.ts`：
```ts
export type GameAudioKey =
  | 'wolf_howl' | 'night_guard' | 'night_wolves' | 'night_seer'
  | 'day_rooster' | 'day_dawn' | 'day_death' | 'day_peaceful';

export interface AudioController {
  play(key: GameAudioKey): Promise<void>;        // resolve 时表示已播完
  playSequence(keys: GameAudioKey[], gapMs: number): Promise<void>;
  stopAll(): void;
  setMuted(muted: boolean): void;
  setVolume(v0to1: number): void;
}
```
- 使用单例 `HTMLAudioElement` 池；同一 key 复用同一元素，重播时 `currentTime=0`。
- 音量从大厅 `SettingsModal` 的音量 slider 同步（`VOLUME_DEFAULT=80`）。
- 浏览器 autoplay 限制：在 LobbyHome → GamePage 切换之前用户必然有 click 交互，所以 GamePage mount 时 audio context 已可用；首次播放前若仍被拒，降级为「静音播放占位 + 提示用户解锁声音」按钮（不在 §6 验收范围内，写成 best-effort）。
- 女巫不使用视频覆盖层，`NIGHT_WITCH` 展示阶段状态与倒计时，并播放 `女巫请睁眼.mp3` 对应的 `night_witch` 音频。

### A.3 音频脚本（与后端节奏对齐）

严格按 `狼人杀需求阐明.md` §二 「第一天黑夜」/「第二天白天」的描述编排。前端在 SSE 事件抵达时按下表触发音频，并**让后端 PacingController 等到音频播完**（前端在播完后通过新接口 `POST /games/{id}/ack`（见 §A.5）告知后端解锁）：

| 触发事件 (SSE) | 前端动作 | 后端等待 |
|---|---|---|
| `phase_enter NIGHT_START` | 1s 停顿 → 播 `wolf_howl` → 播 `night_guard` | 等待 `ack:night_intro_done` |
| `phase_enter NIGHT_WOLF_CHAT` | 1s 停顿 → 播 `night_wolves` | 等待 `ack:night_wolves_done` |
| `phase_enter NIGHT_SEER` | 1s 停顿 → 播 `night_seer` | 等待 `ack:night_seer_done` |
| `phase_enter DAY_ANNOUNCE` | 播 `day_rooster` → 播 `day_dawn` → 若 `death_at_night` 存在则播 `day_death` 否则播 `day_peaceful` | 等待 `ack:day_intro_done` |
| `phase_enter NIGHT_WITCH` | 1s 停顿 → 播 `night_witch`，显示「女巫正在行动」状态与倒计时 | 等待 `ack:night_witch_done` |
| 其余 phase | 无音频 | 无需 ack |

### A.4 倒计时 + 状态显示（聊天框上方）

现 `GamePage` 进入夜晚时（首次出现 `phase_enter NIGHT_*`）：
- 隐藏：`夜深了...` 按钮、`一键分配`、`测试连通性`、`game-seat-badge`（绿色对勾）、`game-stage-debug`。
- 在 `GameChat` 上方挂接 `<GamePhaseHeader />`，包含：
  - 倒计时：从 `phase_enter` 时刻起按 §A.6 时长 countdown。
  - 状态显示：单行中文，例如「守卫正在行动」「狼人正在讨论」「狼人正在行动」「预言家正在行动」「N号玩家正在发言」「正在举行公民投票」「正在 PK 重投」「女巫用药中」。状态文案与 phase 的映射写在 `src/lib/phaseDescriptor.ts`，单元测试覆盖全部 phase。
- 行动状态位置：对话框上方、倒计时下方（对齐需求文档 §三.8）。

### A.5 ack 接口（前端 → 后端）

新增 `POST /games/{id}/ack`：
```jsonc
{ "phase": "NIGHT_START", "event": "night_intro_done", "client_event_id": "..." }
```
- 后端 `GameSession` 在 `PacingController` 中等待对应 ack 信号才继续推进；超时（默认 15s，由 `WH_PACING_ACK_TIMEOUT_MS` 配置）后自动 unblock，记录 hidden `agent_timeout` 事件以便 replay 复盘。
- ack 仅决定**节奏**，不影响 FSM 状态机或事件 hash；`pacing.profile=off` 时后端不等待 ack，前端也不发送。
- ack 不进事件日志（避免污染 replay）；只走内存事件信号。

### A.6 倒计时秒数（需求文档对齐）

| Phase | 倒计时 |
|---|---|
| `NIGHT_GUARD` | 60s（AI 选守护对象） |
| `NIGHT_WOLF_CHAT` | 120s（狼人轮流发言） |
| `NIGHT_WOLF_VOTE` | 30s |
| `NIGHT_SEER` | 60s |
| `DAY_SPEECH`（每位玩家） | 60s + 1s 间隔 |
| `DAY_VOTE` / `DAY_VOTE_PK` | 30s |
| `DAY_LAST_WORDS` | 60s |

这些秒数写入 `configs/games/_rule_sets/majority_or_side_elimination.yaml` 的 `timings` 段；前端从 `GET /games/{id}` 拿到 timings（新增 `GameSummaryResponse.timings`）显示倒计时，后端 PacingController 同源读取，保持单一事实源。

### A.7 高亮特效 / 投票直方图

- **发言高亮**：`GameSeat` 在自己是当前发言者时（`current_speaker_seat === seatIndex+1`）应用 `.game-seat--speaking` 类，CSS 添加 outline + glow + 1s pulse 动画。当前发言者由前端从 `speech` 事件 actor 字段维护（在该 phase 内最后一个 speech 的 actor 即当前发言者）。
- 女巫不新增视频组件；复用 `GamePhaseHeader` 展示 `NIGHT_WITCH` 状态并由音频 ack 对齐 pacing。
- **投票直方图**：在 `GameChat` 通用面板内，`vote_result` 事件触发渲染 `VoteHistogram`（横向条 + 票数）。在 `vote_pk_enter` 时清空，重投后再次渲染。

### A.8 plan.md / architecture.md 同步追加

除 §1 已列内容外，**还需**：

- `plan.md`：在 §1.8 / §1.7 / §3 流程中追加各 phase 的 `timings` 引用；在 §11 列出「STEP-07 引入前端音视频脚本 + ack 节奏接口」。
- `architecture.md`：新增「§16 节奏与音视频对齐」一节，描述 `PacingController` ↔ `ack` ↔ 前端 audio sequence 的握手协议；明确 ack 不进事件日志、不影响 replay hash。
- `.env.example` 追加 `WH_PACING_ACK_TIMEOUT_MS=15000`。

### A.9 测试与验收追加

在 §6 既有验收门基础上**叠加**以下硬指标：

- `tests/unit/test_phase_descriptor.py`（其实在前端 vitest 侧）覆盖所有 phase → 中文文案映射。
- `tests/unit/test_pacing_ack.py`：mock provider 跑一局，断言 `ack` timeout 时 PacingController 仍能推进。
- `tests/integration/test_audio_manifest.py`：断言 `public/assets/game/audio_manifest.json` 9 条游戏音频齐全，`public/assets/game/effect_manifest.json` 6 条图片特效齐全，hash 与素材原文件一致，且不包含视频条目。
- `npm run build` 必须先跑 `copy:game-audio`；CI 在没有 ffprobe 的环境下用预设 duration 也不能失败。
- 手动 smoke 截图新增 2 张：夜晚倒计时 + 女巫状态显示。
- 手动 smoke 录屏（可选，写入 `docs/specs/step-07-smoke.mp4`），证明：入夜音频序列正确、倒计时与状态显示正确、发言高亮、女巫状态显示、结局浮层。

## 9. 不在本步骤范围

- property-based test 扩展（fairness、no-leak、referee-safe 增强）。
- 千局公平性回归脚本与统计报告。
- token 预算 / cost 实测脚本。
- 历史回放页面（消费 `/games/{id}/replay`）。
- 人类入座 + per-seat SSE 鉴权。
- prompt A/B、PromptPack v2。

这些放进 STEP-08 / STEP-09 的候选清单。
