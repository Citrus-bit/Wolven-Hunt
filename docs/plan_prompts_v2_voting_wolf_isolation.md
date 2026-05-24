# Plan: 角色策略提示词 v2 + 同时投票 + 狼人身份隔离根治

## Context

最近几把 AI 对局中观察到三类质量问题，需要一次性收敛：

1. **角色决策不够明智**：当前 `configs/prompts/zh/{role}/{kind}.v1.md` 写的多是"不要做什么"，缺少经典狼人杀的可操作技巧（金水/查杀报法、刀谁、用药时机、守谁、村民站边等），LLM 在关键决策点经常给出业余选择。
2. **顺序投票被复读**：`plan.md` §1.8 写的是"同时投票"，但 `src/wolven_hunt/orchestration/fsm.py:262` 实际是 `for seat in state.alive_seats(): ...` 顺序循环；而 `_apply_vote` (`src/wolven_hunt/core/rule_engine.py:540`) 又把 `vote_cast` 标成 `public_visibility()` 立刻 append，因此后置位的 PlayerView 里能看到已经投出来的票，于是抄前面的票型。
3. **狼人在公共聊天框自爆**：DAY_SPEECH 的 prompt payload (`src/wolven_hunt/llm/prompts.py:38-57`) 把 `wolf_chat_message` / `wolf_kill_vote` / `wolf_kill_decided` 一股脑塞进同一个 `visible_events`，提示词只警告"不要说'我们狼人'"，模型仍会引用、复述狼聊内容把自己暴露在公屏。

目标：一次性升级到 prompt pack v2，并把投票流和狼人身份隔离两个 FSM/Referee 层缺陷修掉。Replay 兼容性靠 `manifest.prompt_pack_version` 区分 v1/v2。

---

## 强制前置：先改 `plan.md`，再改代码

按 `AGENTS.md` 硬性约束 #2，下列规则要先 patch 到 `plan.md` 再动代码：

- §1.8 把"同时投票"明确为「并发收集 + 结算时统一公示」：DAY_VOTE / DAY_VOTE_PK 阶段所有合法投票者基于同一 `event_log` 快照独立决策；中途产生的 `vote_cast` 事件先以 `hidden_visibility()` 暂存（不进入任何玩家的 PlayerView），仅在 phase 结束 `finish_vote` / `finish_pk_vote` 时由 Referee 翻成 `public_visibility()` 并按座位号升序追加到 EventLog。
- §3.3 / §3.4 vote_cast 可见性规则增补：DAY_VOTE / DAY_VOTE_PK 子状态内部的 `vote_cast` 默认 hidden；finish_* 才转 public。`vote_result` 仍然 public。
- §4.4 上下文管理策略：DAY_SPEECH / DAY_VOTE / DAY_VOTE_PK / DAY_LAST_WORDS 阶段，wolf seat 的 prompt payload 中 `visible_events` **必须剔除** `wolf_chat_message`、`wolf_kill_vote`、`wolf_kill_decided` 三类事件；NIGHT_WOLF_CHAT / NIGHT_WOLF_VOTE 才能保留，且改放到独立的 `wolf_private_context` 字段，不进 `visible_events`。
- §5.3 / §6.2 prompt 模板版本 bump 到 `v2`；旧 run 的 `manifest.prompt_pack_version` 仍是 `v1`，`replay_resimulate(config_path=None)` 必须按 manifest 中记录的版本回退。
- §10.2 leakage 测试新增：DAY_SPEECH 阶段 wolf 的 prompt payload 中不得出现上述三类 event type 字符串。
- §10.4 integration 新增：DAY_VOTE 并发收集断言 —— 任意非首位投票者的 PlayerView 在自己 decide 时不能看到本阶段其他人的 `vote_cast`。

> 这一节是 plan.md 的修改清单，写到 plan 文件里，不要在代码层"先做了再说"。

---

## 改动 1：v2 提示词全套（5 角色 × 4 phase + system）

新建 `configs/prompts/zh/{role}/{kind}.v2.md`、`configs/prompts/zh/system.v2.md`，**总行数控制在与 v1 相当**（每个文件 35–55 行，整包 ≤ 950 行）。保留 v1 文件不动，用于回放老 run。

每个角色的核心策略要点（从经典狼人杀通用知识 + 本项目 10 人板规则提炼）：

- **预言家 (seer)**：默认明跳报查；金水比查杀更稳（查杀易被悍跳对冲）；首夜优先查发言矛盾或强带节奏的前置位，不要连查；遗言一次性报完所有查验并留下排查顺序。
- **狼人 (wolf)**：白天采用纯好人视角输出，禁止复述、引用、暗示任何 `wolf_private_context` 中的内容；与队友避免同步表态过强，可适度切割；悍跳预言家仅在队友被强推或己方查杀价值高时启用；投票理由必须能在公开发言中自洽。
- **女巫 (witch)**：首夜默认救（信息价值最大），首夜后视刀口判断；预言家明跳且可信优先救预言家；毒药只用于高置信狼坑且需要白天公开行为佐证；每晚最多一瓶；白天不无收益跳身份，不主动报剩余药品状态。
- **守卫 (guard)**：首夜倾向守发言强的好人或自守；预言家明跳且可信后优先守预言家；切勿连守同一目标；平安夜与守护目标一致时可酌情公开协助查狼；遗言报关键夜守护对象。
- **村民 (villager)**：不要乱跳神；重点抓发言矛盾、票型摇摆、强推可信好人的玩家；跟可信预言家走，被悍跳时结合女巫/守卫的公开线索判断真预；投票果断站边，最后一刀往往最关键。

每个 v2 文件结构沿用 v1：身份 → 当前阶段 → 行动指令 → 策略建议（升级核心区）→ 输出格式。**新增统一围栏**：所有 wolf 模板必须加一段"在 DAY_* 阶段你不会看到 `wolf_private_context`；任何关于狼聊/狼刀的文字都不能出现在你的 DAY_SPEECH / DAY_VOTE / DAY_LAST_WORDS 输出中"。

同步把 v2 写入默认渲染路径：
- `src/wolven_hunt/llm/prompts.py:23` `PromptRenderer(..., version="v1")` → default `"v2"`
- `src/wolven_hunt/llm/gateway.py:85` `prompt_version: str = "v1"` → `"v2"`
- `src/wolven_hunt/orchestration/runtime.py:473,614` 两处 `"v1"` 字面量 → `"v2"`
- `src/wolven_hunt/cli.py:93` manifest 写入的 `"prompt_pack_version": "v1"` → `"v2"`
- `src/wolven_hunt/storage/replay.py:81` `replay_resimulate` 默认仍读 manifest 中的版本；缺失字段时回退 `"v1"` 兼容老 run。

---

## 改动 2：同时投票（并发收集 + 结算时统一公示）

核心改动集中在 `src/wolven_hunt/orchestration/fsm.py` 的 `_run_day` 中 DAY_VOTE / DAY_VOTE_PK 两段（line 261–311），以及 `_apply_vote` / `_apply_pk_vote` 的 visibility 规则。

### 2.1 Visibility 改动（`src/wolven_hunt/core/rule_engine.py:530-559`）

`_apply_vote` 和 `_apply_pk_vote` 生成的 `VOTE_CAST` 事件改用 `hidden_visibility()`，payload 不变。`finish_vote` (`rule_engine.py:251`) 与 `finish_pk_vote` (`rule_engine.py:303`) 在产出 `VOTE_RESULT` / `VOTE_PK_ENTER` 之前，先回扫本阶段所有 hidden 的 vote_cast，逐条改写成 public visibility 并按 actor seat 升序追加到事件列表。

`VOTE_CAST` 改为 hidden 之后，前端 `latestVoteCounts`（`src/components/Game/GameChat.tsx:305`）和 `VoteHistogram` 仍能用 `vote_result` 里的 `counts` 渲染直方图，无需改动。spectator API (`GET /games/{id}/events`) 走 `filter_spectator_events`：hidden 期不暴露，公示后正常推出。

### 2.2 FSM 并发收集（`src/wolven_hunt/orchestration/fsm.py:261-311`）

引入轻量 helper `_collect_votes_concurrently(state, config, agents, event_log, voters, decide_fn, rng)`：
- 在循环开始**前**冻结 `snapshot_events = event_log.events` 和 `snapshot_state = state`。
- 用 `concurrent.futures.ThreadPoolExecutor(max_workers=len(voters))` 对每个 voter 并行执行 `build_view(snapshot_state, snapshot_events, ...)` → `agent.decide_vote(view)` → Pydantic / `validate_action` / fallback 流程。沿用现有 `_decide_with_fallback` 的语义，把它拆成 `_resolve_action(snapshot_state, snapshot_events, agent, seat, decide_fn, rng)` 返回 `(action, error_events)`，**不直接 append vote_cast**。
- 收集完所有 `(seat, action, error_events)` 后，**回主线程**按 `voters` 的座位序确定性 append：先按座位号升序追加 `error_events`（agent_invalid_action / agent_fallback_triggered / llm_call），再调用 `apply_action` 产生 hidden `vote_cast` 事件并 append。这一步保证 seq 严格递增、replay_resimulate 一致。
- 然后调用 `finish_vote(state)` 完成翻 public + 公示。

DAY_VOTE_PK 完全复用同一 helper，只是 voters 来自 `state.alive_seats() - state.pk_seats`、decide_fn 改为 `decide_pk_vote`。

LLM provider 的 timeout / retry / fallback 全部走原有路径（不动 `_decide_with_fallback` 内部对 `LLMFallbackRequired` 的处理），只在 append 时机上抽出来。ThreadPoolExecutor 不破坏 `rng` 的确定性，因为 fallback 抽样仍按座位号串行触发。

### 2.3 NIGHT_WOLF_VOTE 是否同改

不动。`plan.md` §1.6 明确狼队"同时提交刀人目标"，但狼队夜聊本身就让狼人对刀口达成共识，且现有顺序提交在产品体验上没有用户抱怨。本次只修 DAY_VOTE / DAY_VOTE_PK。若未来狼人决策也想并发，可复用同一 helper。

---

## 改动 3：狼人身份隔离（Referee 层 + Prompt 层双管）

### 3.1 Prompt payload 重构（`src/wolven_hunt/llm/prompts.py:38-57`）

修改 `PromptRenderer.render`：
- 新增局部常量 `WOLF_PRIVATE_EVENT_TYPES = frozenset({"wolf_chat_message", "wolf_kill_vote", "wolf_kill_decided"})`。
- 当 `view.self_role is Role.WOLF` 且 `phase` 属于 `{"DAY_SPEECH", "DAY_VOTE", "DAY_VOTE_PK", "DAY_LAST_WORDS"}` 时，把这些类型加入 `exclude_event_types`，使它们**完全不出现**在 `payload["visible_events"]` 里。
- 当 `view.self_role is Role.WOLF` 且 `phase` 属于 `{"NIGHT_WOLF_CHAT", "NIGHT_WOLF_VOTE"}` 时，从 `view.visible_events` 抽出这些类型组成独立的 `payload["wolf_private_context"]`（结构同 `_event_to_prompt_dict`），同时也从 `payload["visible_events"]` 中剔除避免重复。其它角色 / 其它 phase 的 payload 不含 `wolf_private_context` 字段。
- `exclude_event_types` 现在是基于 `phase` + `role` 的派生集合，不再硬编码 `{"speech"}`。

`build_prompt_visible_events` (`src/wolven_hunt/llm/context.py:47`) 已经支持 `exclude_types`，无需改动。

### 3.2 Prompt 文本强化（v2 wolf 模板）

`configs/prompts/zh/wolf/speech.v2.md`、`vote.v2.md`、`last_words.v2.md` 加显眼围栏（用 markdown blockquote 或 `>>> 禁令`），明确：
- "你在 DAY_* 阶段的 payload 不会包含 `wolf_private_context`；任何来自夜聊和狼刀的细节都不在你白天可见的事实集合内。"
- "禁止在输出文本中复述、引用、暗示、用第一人称转述 `wolf_chat_message` / `wolf_kill_vote` / `wolf_kill_decided` 的内容；禁止使用'我们昨晚'、'狼队'、'我刀'、'兄弟'、'同伴'、'队友'、'我们决定'这类表达。"
- "你的发言只能基于 `visible_events` 中的公开事件、`own_public_speeches`、`prior_public_speeches`。"

`configs/prompts/zh/wolf/night_action.v2.md` 反过来引导：夜聊和投刀在 `wolf_private_context` 里，可以引用以做团队协同；同时禁止在 wolf_chat_message 里写任何会被白天复读的 quote-able 句式。

`configs/prompts/zh/system.v2.md` 的"信息边界"小节加一行：wolf 在白天阶段的 payload 中**不存在** `wolf_private_context`；如果模型臆造该字段视为合规违规。

### 3.3 Leakage 测试（`tests/leakage/test_prompt_leakage.py`）

新增三个用例（同一文件追加）：
1. wolf seat + DAY_SPEECH：`PromptRenderer.render` 输出的 prompt 字符串中不能出现 `"wolf_chat_message"`、`"wolf_kill_vote"`、`"wolf_kill_decided"` 子串，也不能出现 wolf_chat 的原始 text 内容。
2. wolf seat + NIGHT_WOLF_CHAT：payload 中存在 `"wolf_private_context"` 字段，`"visible_events"` 中 **不再** 含上述类型，且 wolf 自己的 chat / vote 出现在 `wolf_private_context` 里。
3. 非 wolf seat + 任意 phase：payload 中不存在 `"wolf_private_context"` 字段（防止误注入）。

---

## 涉及文件清单

> 以"模式 + 代表路径"描述，不逐行列出。

### 必改

- `plan.md` — §1.8 / §3.3 / §3.4 / §4.4 / §5.3 / §6.2 / §10.2 / §10.4 按本文 Context 上方"强制前置"小节更新。
- `configs/prompts/zh/system.v2.md` — 新建。
- `configs/prompts/zh/{seer,wolf,witch,guard,villager}/{night_action,speech,vote,last_words}.v2.md` — 新建（共 20 个，wolf 4 个加身份隔离围栏，其他角色加策略 bullet 升级）。
- `src/wolven_hunt/llm/prompts.py` — 默认 version 改 `v2`；按 role+phase 派生 `exclude_event_types`；wolf night phase 注入 `wolf_private_context`。
- `src/wolven_hunt/llm/gateway.py:85` — 默认 `prompt_version="v2"`。
- `src/wolven_hunt/orchestration/runtime.py:473,614` — 两处 `"v1"` → `"v2"`。
- `src/wolven_hunt/orchestration/fsm.py` — 拆出 `_resolve_action(...)` 与 `_collect_votes_concurrently(...)`；`_run_day` 中 DAY_VOTE / DAY_VOTE_PK 改用并发收集 + 排序 append。
- `src/wolven_hunt/core/rule_engine.py` — `_apply_vote` / `_apply_pk_vote` 改 `hidden_visibility()`；`finish_vote` / `finish_pk_vote` 内部按座位号升序把 hidden vote_cast 翻 public 并补入返回 events 元组。
- `src/wolven_hunt/cli.py:93` — manifest `prompt_pack_version` 改 `"v2"`。
- `src/wolven_hunt/storage/replay.py:81` — 改成读 manifest 中记录的 version；缺失时回退 `"v1"`。

### 测试

- `tests/leakage/test_prompt_leakage.py` — 追加 3 个 wolf payload 隔离用例（见 §3.3）。
- `tests/integration/test_fsm_full_loop.py` — 追加并发投票断言：在 DAY_VOTE 之前 snapshot `event_log.events`，确保 decide_vote 期间任何 voter 的 PlayerView `visible_events` 都不包含本阶段他人的 `vote_cast`；finish_vote 之后 `vote_cast` 又应当公开。
- `tests/golden/` — 既有 fixture 用的是 mock provider 与固定 seed，prompt 版本升级会改 prompt_hash，需要 regenerate 黄金日志或在 fixture 里固定 `prompt_version="v1"` 跑兼容用例。建议加一个**新的** golden case 跑 v2，并保留旧 case 跑 v1。

### 文档

- `docs/specs/` 下不动（STEP-07 已发布）；如有 STEP-08 文档涉及 prompt pack 版本，同步指出 v2 升级点。

---

## 验证方式

1. **静态**：`ruff` / `pyright` / `npm run typecheck`（前端无改动应零警告）。
2. **单测 + 集成**：`pytest tests/leakage/test_prompt_leakage.py tests/integration/test_fsm_full_loop.py -x` 全部绿；新增的并发投票断言、wolf payload 隔离用例显式覆盖问题场景。
3. **黄金回放**：`pytest tests/golden/` 通过；新建一个 `golden/v2_classic_10/` fixture 验证 v2 prompts 下 100 局 mock 跑通 + replay_resimulate 一致；旧 v1 fixture 仍能 resimulate（manifest 写 v1）。
4. **真实 LLM smoke (可选)**：开启 `WH_LLM_PROVIDER=litellm` + 真实 key 跑一局 10 模型对战，人工观察：
   - 狼人 DAY_SPEECH 中不再出现"我们昨晚 / 狼队 / 我刀 / 队友"等口吻。
   - 后置位玩家在 DAY_VOTE 决策时不再明显跟随前置位（看 `narrative.jsonl` 时间序）。
   - 预言家 / 女巫 / 守卫 / 村民的发言更贴近经典玩法（明跳金水、首夜默认救、明牌起跳等）。
5. **前端冒烟**：`npm run dev` 起前端 7001、后端 7002，跑一局到 DAY_VOTE 阶段确认：聊天框直方图在 `vote_result` 之后才出现完整票型，过程中不会逐张刷新（因为 vote_cast 已 hidden）。
