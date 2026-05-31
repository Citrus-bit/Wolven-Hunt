# Wolven Hunt Architecture Contract

本文档是 `plan.md` 的架构契约落地版。后续实现必须以 `plan.md` 为基准，并以本文档作为首期架构契约。若两者发生冲突，先更新 `plan.md`，再同步本文档和代码。

## 1. Scope

首期目标是一个可复现、配置驱动、事件日志为单一事实源的 10 人狼人杀引擎骨架。

首期固定板子：

- 狼人 3 人
- 村民 4 人
- 预言家 1 人
- 女巫 1 人
- 守卫 1 人

当前阶段为 STEP-07 / P3 观赛 MVP：允许在 STEP-06 外部接入基础上实现 per-seat LLM provider 路由、观赛 pacing/ack、叙事化事件流、角色揭晓、前端音视频、倒计时、投票直方图、女巫夜晚行动状态与终局定格态。

`DAY_SPEECH` / `DAY_LAST_WORDS` 输出必须经过 Referee 文本事实一致性 hook；确定性违反规则机制、本人私有行动历史或越权私有事实的文本按 `illegal_action` 处理，不得进入 EventLog、narrative、spectator API 或 SSE。

STEP-07 同时允许默认关闭的 Prompt Evolution 子系统。该子系统只通过配置开关启用，基于已结束对局的 `review_report.json` 生成新提示词整包快照；不得修改事件 schema、胜负判定、Referee 权限边界、普通 PlayerView、spectator 投影或 replay/resimulate 语义。

STEP-07 允许单真人玩家模式：一局最多 1 个真人座位，其余座位由 AI 托管。真人只能访问自己座位的 PlayerView，座位 SSE 和动作提交必须通过绑定 seat 的 `player_token` 鉴权。真人回合的 `turn_request` / `turn_cleared` 只是 SSE 投影，不进入 EventLog，不影响 replay hash、胜负判定或 resimulate 事件 schema。

## 2. Rule Contract

`GameConfig = RolePack + RuleSet + ModelRoster + PromptPack + random_seed`

新增板子时只能通过配置扩展，不改核心引擎代码。每局 `game_start` 必须记录：

- `random_seed`
- `config_hash`
- `seat_range`
- `role_assignment`

这些 metadata 用于 replay 校验。进入 PlayerView 前必须由 Referee 脱敏。

每局 manifest 必须记录启动时实际使用的 `prompt_pack_version`。Prompt pack 版本使用整包不可变快照：旧版本文件不得就地覆盖或删除，新增版本必须包含 `system` 与所有角色 action prompt 文件。自动进化只能改写目标角色的 `speech`、`vote` 或 `night_action` 文件；`system` 与 `last_words` 不参与自动进化。

含真人局的 manifest 还必须记录：

- `human_seat`
- `seat_agent_kinds`
- `forced_seat_roles`

真人建局可选择指定座位或随机座位，并可将真人角色指定为 `villager`、`witch`、`seer`、`guard`、`wolf` 或 `random`。非 `random` 时，发牌先按 seed 完成 deterministic shuffle，再把真人座位当前角色与目标角色所在座位做 swap；该机制不得改变角色计数。`forced_seat_roles` 必须随 manifest 持久化，`replay_resimulate` 重跑发牌时必须读回并透传；真人具体动作在 resimulate 中不保证复现，但 deterministic replay 从 EventLog 可还原。

座位统一使用 1-based 编号，默认固定为 1 到 10 号。`GAME_START` 使用 `random_seed` 派生的 deterministic RNG 洗牌分配角色。玩家只知道自己的角色；狼人额外知道全部狼队同伴身份；STEP-07 起 spectator 是观众上帝视角，可看到全部座位身份、狼人夜聊和 spectator-only 观赛特效，但仍不得看到 raw response、provider 配置、守卫/预言家私有结果、女巫私有结果或狼队投刀事件原文。

## 3. Win Condition

每次夜晚结算后立即执行胜负检查；投票放逐后若有放逐者先执行其遗言，再执行胜负检查。

狼人胜：

- `alive_wolves > alive_good_players`
- 或 `alive_villagers == 0`
- 或 `alive_gods == 0`

好人胜：

- `alive_wolves == 0`

胜负规则写入 `configs/games/_rule_sets/majority_or_side_elimination.yaml`，并由 `RuleSet.win_conditions` 配置驱动执行。神职边为好人阵营中非 `villager` 的角色，当前为预言家、女巫、守卫。

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
- 守卫只影响狼刀，不阻止女巫毒药。

### Wolves

- 每晚最多 1 轮夜聊，每狼一句；运行时必须按存活狼人 seat 升序逐席收集并立即追加 `wolf_chat_message`，后一位狼人通过 Referee 过滤后的狼队视角可看到前序狼聊。
- 随后同时提交刀人目标；运行时可基于同一份夜晚 snapshot 并发收集，结算仍按 actor seat 升序执行。
- 多数决定刀人目标。
- 平票时在被狼队投到的目标中 deterministic random 选择，并记录 `wolf_tie_random`。
- 合法刀人目标是所有存活非狼玩家或狼人自己。
- 合法刀人目标以整轮 `NIGHT_WOLF_VOTE` 为单位校验：狼人可以投任一存活非狼玩家，也可以投自己自刀；`wolves.can_follow_teammate_self_kill: true` 时，若一名狼人本轮也投自己，其他狼人可以跟票该自刀目标。不允许单方面刀未自投的狼队友，不允许空刀。
- 狼队投刀事件仅狼队可见；狼人夜聊对狼队玩家和 STEP-07 spectator 上帝视角可见。

### Witch

- 女巫属于好人阵营，每局拥有 1 瓶解药和 1 瓶毒药。
- 女巫每晚在狼人投刀后、预言家查验前行动；女巫死亡后不再行动。
- 女巫知道当晚狼刀目标。解药只能救当晚狼刀目标；毒药可以毒任意存活其他玩家，不能毒自己。
- 每晚最多使用一瓶药，可以选择 `save`、`poison` 或 `skip`；解药和毒药每局各最多使用一次。
- 若守卫守护目标和女巫解药目标同为当晚狼刀目标，则判定为双奶死亡，该目标死亡。
- 守卫不挡毒药。若毒药命中目标，该目标死亡；若毒药目标同时也是狼刀目标，按毒药参与死亡处理。
- 女巫行动生成私有 `witch_action` 事件，仅女巫本人可见。

### Villager

- 无夜晚主动技能。
- 白天参与发言、投票、PK 重投和公开流程。

## 5. Day, Vote, Last Words

首夜可以死亡，`first_night_can_die: true` 是首版默认。

首夜死亡在首日 `DAY_ANNOUNCE` 公示。首夜狼刀死亡和双奶死亡者进入首日 `DAY_LAST_WORDS`；毒药导致死亡任何情况下无遗言。第二夜及之后的夜晚死亡者无遗言。

白天按座位顺序一轮发言，每名存活玩家一次，中文默认 300 字上限。

白天发言和遗言允许正常身份伪装、诈身份和策略性判断；但 Referee 必须拦截确定性不可能或越权的文本事实，例如守卫声称连续两晚守同一人、守卫把“守护成功/挡刀成功”说成确定事实、玩家引用未授权狼聊/狼刀/模型/provider/raw response 作为可见事实。

`DAY_SPEECH` 中，尚未完成当前白天公开发言的存活座位只能视为未轮到。玩家不得把这类座位说成不报查验、未回应、沉默、划水、不活跃、发言少或藏身份；Referee 文本事实一致性 hook 必须按 `illegal_action` 拒绝该类输出并触发重试与 fallback。

每日 `DAY_SPEECH` 发言起点优先由最近一次夜晚公布死亡决定：若 `state.last_night_deaths` 非空，以其中座位号最大的死亡玩家为锚点，从其下一位存活玩家开始，按座位号递增循环一圈并跳过死亡玩家。若当晚无人死亡，则回退 `rule_set.first_speaker_seat`（默认 1 号）作为起点。该规则只影响 `speech` 事件 actor 顺序，不新增事件类型，也不改变投票、遗言、PK 或 replay schema。

投票规则：

- 同时投票。
- 公开票型。
- 允许弃票。
- 不允许改票。
- 无警长。
- 首轮投票只能投存活玩家。
- 允许投自己。
- 不能投已死亡玩家。
- `DAY_VOTE` / `DAY_VOTE_PK` 的同时投票必须基于同一份 `GameState` 与 `EventLog` 快照收集所有合法投票者决策。运行时可并发调用各 Agent；结算前投票决策只保存在 FSM 内存 pending action 中，不写入 EventLog、不进入 PlayerView、prompt、spectator API 或 narrative。结算时按 actor seat 升序追加公开 `vote_cast`，再追加 `vote_result` / `vote_pk_enter` / `exile` / `peaceful_day`。弃票的 `vote_cast` payload 固定为 `{target: null, abstain: true}`；`vote_result` payload 必须包含 `counts`、`tied`、`abstain_count`、`abstentions`。弃票公开展示但不进入 `counts`，不参与最高票或平票候选；全员弃票直接平安日。EventLog append-only，不允许回写修改历史事件。

首轮平票进入 `DAY_VOTE_PK`。平票玩家各一次 PK 发言后重投。PK 重投只能投 PK 台上的存活玩家，PK 台上玩家不参与重投。首轮或 PK 重投全员弃票均直接平安日；PK 第二次仍平票则平安日，直接入夜。

白天被正常投票或 PK 重投放逐的玩家在 `DAY_EXILE` 后进入 `DAY_LAST_WORDS`，遗言完成后再执行白天胜负检查。二次平票或无人可投导致的平安日不触发遗言。

有遗言：

- 白天被放逐者
- 首夜狼刀死亡者
- 首夜双奶死亡者

无遗言：

- 第二夜及之后的夜晚死亡者
- 任何夜晚被毒药导致死亡者

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
    -> NIGHT_WITCH
    -> NIGHT_SEER
    -> NIGHT_RESOLVE
    -> CHECK_WIN
  -> DAY_ANNOUNCE
    -> DAY_LAST_WORDS?
    -> DAY_SPEECH
    -> DAY_VOTE
    -> DAY_VOTE_PK?
    -> DAY_EXILE?
    -> DAY_LAST_WORDS?
    -> CHECK_WIN
  -> loop NIGHT_START
GAME_END
```

女巫行动是固定夜晚子状态 `NIGHT_WITCH`，位于狼人投刀后、预言家查验前。只要当前 RolePack 包含女巫，STEP-07 live 观赛每晚都进入 `NIGHT_WITCH` 并追加 `phase_enter` / `phase_exit`；只有女巫存活且仍有至少一瓶药时才调用 Agent 并生成 `witch_action`。女巫无药或死亡时该 phase 只承担主持和音频 pacing，不调用 Agent，不生成私有行动事件、`llm_call` 或 fallback。白天不再存在中断技能。现场观赛时前端在 `NIGHT_WITCH` 播放 `night_witch` 音频并通过 `ack:night_witch_done` 解除 pacing 等待；ack 不进入 EventLog、不影响 replay hash。

STEP-07 live 观赛中，`NIGHT_GUARD`、`NIGHT_WITCH`、`NIGHT_SEER` 同时承担公开主持与音频 pacing。只要 RolePack 包含对应角色，每晚都进入该 phase 并追加 `phase_enter` / `phase_exit`。若对应神职已死亡，或女巫已无可用药，该 phase 只用于观赛节奏，不调用死亡/无行动资格 Agent，不生成 `guard_protect`、`witch_action`、`seer_check`、`seer_check_result`、`llm_call` 或 fallback 事件。前端收到死亡神职 phase 时必须完整播放对应夜晚音频，再固定等待 5 秒后发送 ack；ack 只解除现场 pacing，不进入 EventLog、不改变 replay/resimulate 语义。

## 8. Night Resolve

`NIGHT_RESOLVE` 顺序固定：

1. 读取本晚守卫目标 `G`、狼刀目标 `K`、女巫动作 `W`、预言家目标 `S`。
2. 若 `K` 存在且 `W == save(K)` 且 `G == K`，`K` 双奶死亡。
3. 若 `K` 存在且 `W == save(K)` 且 `G != K`，`K` 存活。
4. 若 `K` 存在且 `W != save(K)` 且 `G == K`，生成 `no_death_tonight`；否则 `K` 死亡。
5. 若 `W == poison(P)`，`P` 额外死亡；如果 `P == K`，死亡只记录一次，并标记为毒药参与死亡。
6. 无死亡时生成 `no_death_tonight`；有死亡时为每个死亡 seat 生成 `death_at_night`。死亡事件不暴露死因。
7. 首夜狼刀死亡和双奶死亡触发 `DAY_LAST_WORDS`；毒药导致死亡无遗言；第二夜及之后夜死无遗言。
8. `seer_check_result` 在 `NIGHT_SEER` 结束时已生成，结算阶段不再处理。

同夜信息可见性：

- 狼人不知道今晚是否被守。
- 女巫只在 `NIGHT_WITCH` 自己的 PlayerView 中看到当晚狼刀目标和药品剩余状态；其他玩家与 spectator 不可见。
- 预言家查验结果在 `NIGHT_SEER` 结束时立即对本人可见。
- 守卫不知道自己是否守住狼刀。
- `last_guard_target` 只允许在守卫本人 `NIGHT_GUARD` PlayerView 的 `rule_set_summary` 中出现，用于合法性约束；spectator、非守卫玩家、守卫的非守卫行动阶段均不可见。

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
- 夜晚：`guard_protect`, `wolf_chat_message`, `wolf_kill_vote`, `wolf_kill_decided`, `wolf_tie_random`, `witch_action`, `seer_check`, `seer_check_result`, `no_death_tonight`, `death_at_night`
- 白天：`day_announce`, `last_words`, `speech`, `vote_cast`, `vote_result`, `vote_pk_enter`, `peaceful_day`, `exile`
- 系统：`win_check`, `agent_timeout`, `agent_invalid_action`, `agent_fallback_triggered`, `agent_budget_warning`
- 元数据：`llm_call`

`vote_cast` 只在投票 phase 结算时公开追加；投票收集过程中不得提前写入 EventLog。弃票 `vote_cast` 使用 `{target: null, abstain: true}`。`vote_result` 仍然 public，`counts` 只统计非弃票目标，并通过 `abstain_count` / `abstentions` 暴露弃票数量与座位，继续作为前端直方图与叙事票型来源。

`llm_call` 包含 `prompt_hash`、`raw_response_hash`、`storage_ref`、`model`、`prompt_tokens`、`completion_tokens`、`cost_usd`、`prompt_version`，但仅写入存储层，不进入 PlayerView。完整 raw response 仅写入私有存储；`llm_call` payload 不得包含 raw response 原文。

Prompt Evolution 的 raw response 若保存，只能写入私有 `runs/_evolution/raw_responses.jsonl`。进化状态、ledger、候选 diff 和 prompt 文件版本不进入普通 EventLog，不影响 replay hash；回放必须始终使用 manifest 中记录的 `prompt_pack_version`。

`role_reveal` 仅在 `GAME_END` 后由 Referee 生成，公开可见，payload 固定为 `{winner, seats: [{seat, role, alive}], highlights}`。`pacing_tick` 是未来保留事件；STEP-07 不写入事件日志，避免污染 replay hash。

所有随机事件 payload 必须记录：

- `rng_stream`
- `candidates`
- `selected`
- `reason`

`turn_request` / `turn_cleared` 不是 EventLog 事件。它们只通过真人座位 SSE 下发，`turn_request` payload 固定包含 `seat`、`kind`、`deadline_ts`、`timeout_seconds`、`valid_targets`、`constraints`、`phase`、`day`。合法目标与约束必须由后端根据 Referee PlayerView 和 RuleSet 计算，前端只能渲染，不得自行判定行动合法性。

## 10. Visibility

可见性由 Referee 统一处理。

- 公共事件：所有玩家可见，包括死亡 Agent。
- 狼队事件：`wolf_kill_vote`、`wolf_kill_decided`、`wolf_tie_random` 仅狼队 seat 可见；`wolf_chat_message` 对狼队 seat 和 STEP-07 spectator 上帝视角可见。
- 私有事件：仅 actor 或白名单 seat 可见。
- `llm_call`、raw response 存储引用默认不进入任何 PlayerView。完整 `role_assignment` 只允许进入 spectator 上帝视角和存储/调试工具，不进入普通玩家 PlayerView。
- 狼人白天 prompt 额外执行上下文隔离：`DAY_SPEECH`、`DAY_VOTE`、`DAY_VOTE_PK`、`DAY_LAST_WORDS` 中，wolf seat 的 prompt payload `visible_events` 必须剔除 `wolf_chat_message`、`wolf_kill_vote`、`wolf_kill_decided`、`wolf_tie_random`，且不得注入 `wolf_private_context`。`NIGHT_WOLF_CHAT` / `NIGHT_WOLF_VOTE` 中，wolf seat 可通过独立 `wolf_private_context` 字段接收这些狼队私有事件，同类事件不得重复出现在 `visible_events`。
- 真人座位流必须使用 `build_view(..., seat=Seat(n))`，不能复用 spectator 上帝视角。同 seq `narrative_row` 与 `spectator_effect` 投影必须按来源事件复用该座位可见性。真人死亡后继续连接同一座位流，只接收该座位可见的后续公开信息；整局结束后才可通过 reveal/复盘看到全局翻牌。

## 10. Human Player API Contract

`POST /games` 可接受 `human_seat`、`human_seat_random`、`human_role`。`human_seat` 与 `human_seat_random=true` 互斥；纯 AI 局不签发 token。有真人时响应返回 `player_token` 与 `human_seat`，并为该座注入昵称 `你自己` 和 `/assets/lobby/human_player.png`，除非调用方已显式提供该座展示信息。

`GET /games/{game_id}/seat/{seat}/stream` 是座位过滤 SSE，必须校验 query token 或 Authorization bearer token。流中可以包含按座位过滤的 `game_event`、同 seq narrative/effect 投影，以及当前 active turn 的 `turn_request` / `turn_cleared`。

`POST /games/{game_id}/seat/{seat}/action` 是真人统一动作提交端点，支持 `guard`、`wolf_chat`、`wolf_vote`、`seer`、`witch`、`speech`、`vote`、`pk_vote`、`last_words`。服务端必须先验证 token 与 active turn 的 seat/kind，再构造 Action，执行 `validate_action`；文本类还必须执行 `validate_text_consistency`。合法动作进入 pending 队列，非法返回 422 且 active turn 保持可提交。

真人超时由 `HumanInputAgent` 处理：设置 turn 后阻塞等待 pending action，超时则清除 turn 并调用 base Agent 接管当前回合。超时本身不产生 EventLog 特殊事件。

含真人的完成局必须在 Prompt Evolution 的 `record_finished_game` 阶段写入 `game_ignored(reason="human_player")` 并直接返回，不进入 baseline 或 challenger 窗口；复盘生成不受影响，且 per-seat dossier 可使用 manifest `seat_agent_kinds` 标记 `agent_type`，用于让真人座位的复盘措辞体现真人玩家身份。

PlayerView 中的 `game_start` 必须脱敏：

- 本人看到自己的角色。
- 狼人看到狼队同伴。
- spectator 上帝视角看到完整 `role_assignment`，用于观赛身份徽标。

Referee 是唯一权限边界。核心规则和 Agent 不得自行拼接越权视角。

## 11. LLM Errors and Fallback

三类异常：

- 超时：单次调用超过 `llm.timeout_seconds`；若 RuleSet 配置 `fallback.phase_timeout_seconds[phase]`，该阶段使用覆盖值。
- 非法 JSON 或 schema 校验失败。
- 合法性校验失败：结构合法但违反规则，或 `DAY_SPEECH` / `DAY_LAST_WORDS` 文本事实一致性 hook 拒绝。

错误子类映射到外显事件：`timeout` / `rate_limit` / `network` 归为 `agent_timeout`；`invalid_json` / `schema_violation` / `illegal_action` 归为 `agent_invalid_action`。

每阶段每 Agent 最多重试 `fallback.max_retries` 次，默认 2 次；若 RuleSet 配置 `fallback.phase_max_retries[phase]`，该阶段使用覆盖值。当前默认配置不再设置阶段级重试覆盖，确保正式对局 LLM 失败后按统一节奏重测。运行时必须优先使用 RuleSet 中的 retry 配置，环境变量只能作为 provider/default 配置来源，不能覆盖已加载 RuleSet 的阶段重试契约。重试 prompt 末尾追加：`上一次输出未被接受：{error_type}: {message}。请只返回符合 schema 的 JSON。` 失败后若仍有重试预算，按 RuleSet 中的固定退避序列 `retry_backoff_delays_seconds` 等待；当前默认序列为 `[1, 2]`，其中首次失败后的 `attempt=0` 使用 1 秒。超过序列长度的额外重试复用最后一个延迟。旧的指数退避字段仅作为旧配置兼容输入，不得覆盖显式固定序列。当前默认 `retry_backoff_jitter: false`，不得引入未记录或不可复现的随机 jitter。通过 schema 但被 Referee 行动校验或文本事实一致性 hook 拒绝时，记录 `agent_invalid_action`，按同一阶段重试预算要求 Agent 重选/重写；重试仍失败则触发 fallback，并记录 `agent_fallback_triggered`。

默认 fallback：

| 阶段 | Fallback |
|---|---|
| `NIGHT_GUARD` | 随机选一个合法目标，排除昨晚守护对象 |
| `NIGHT_WOLF_CHAT` | 发送空消息，占位为 `[沉默]` |
| `NIGHT_WOLF_VOTE` | 随机选一个存活非狼或自己（fallback 不主动创建队友自刀跟票） |
| `NIGHT_WITCH` | 默认跳过，不消耗药品 |
| `NIGHT_SEER` | 随机选一个非自己玩家 |
| `DAY_SPEECH` | 基于 Referee 过滤后 PlayerView 的确定性公开发言模板 `contextual_public_speech` |
| `DAY_VOTE` | 随机选一个存活玩家，允许自己，fallback 不主动弃票 |
| `DAY_VOTE_PK` | 台下玩家随机投一个 PK 台上存活玩家；如无台下玩家可投，直接平安日 |
| `DAY_LAST_WORDS` | 默认模板 `我没有遗言` |

所有 fallback 行为写入 RuleSet。所有 fallback 随机使用 deterministic RNG，并记录候选集、选中值与 fallback 原因。`contextual_public_speech` 只能读取当前 seat 的 PlayerView、公开/本人可见事件与 rule summary；不得读取 raw response、provider 配置、spectator-only 投影或任何未授权私有事件。默认固定退避配置为：`retry_backoff_delays_seconds: [1, 2]`、`retry_backoff_jitter: false`。默认阶段超时覆盖为：`DAY_SPEECH` 使用 18 秒超时；`NIGHT_WOLF_CHAT` 使用 10 秒超时；`NIGHT_WOLF_VOTE`、`DAY_VOTE` 与 `DAY_VOTE_PK` 使用 6 秒超时；`NIGHT_GUARD`、`NIGHT_WITCH` 与 `NIGHT_SEER` 使用 10 秒超时；所有阶段默认沿用 `fallback.max_retries: 2`。默认观赛 pacing 倒计时与 LLM 单次超时分离：`DAY_SPEECH` 60 秒，`NIGHT_WOLF_CHAT` 90 秒，`NIGHT_WOLF_VOTE` / `DAY_VOTE` / `DAY_VOTE_PK` 30 秒，`NIGHT_GUARD` / `NIGHT_WITCH` / `NIGHT_SEER` 20 秒；ack 仍只控制现场观赛节奏，不写入 EventLog，不影响 replay hash。

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
configs/prompts/zh/seer/night_action.v5.md
```

事件日志记录 `prompt_version`，用于解释当前仓库仍保留的 prompt pack。

提示词渲染顺序固定为：

```text
[system.{version}.md] + [role/phase.{version}.md] + [JSON payload] + [retry_error?]
```

`system.v5.md` 是当前默认全员统一系统提示词；角色/phase 模板来自 `configs/prompts/{language}/{role}/{kind}.v5.md`。旧玩家行动 prompt `v1` / `v2` / `v3` / `v4` 已外置归档到 `/Users/tampouseng/Desktop/Wolven Hunt 废案/2026-05-29-repo-cleanup/configs/prompts/`，不再作为运行时或 replay/resimulate 兼容输入。`v5` 继承旧版本的高信息密度、禁止占位废话、白天发言 2-4 句等约束和角色策略，并增强狼人夜间刀口判断与白天事实边界：首夜平安夜应优先按女巫救人高概率评估，不得仅因无人死亡就认定首夜刀口被守卫守护；第二夜若可信预言家已暴露，即使首夜刀口在外置位，也要把守卫今晚可能守预言家作为主要风险；守卫不可连续守同一目标只能用于真实高置信的上一夜守护目标，不能机械套用到可能被女巫救下的首夜刀口。狼人仍不得机械刀守卫大概率守护的明预，可换刀女巫、守卫、强民或外置神，并可少量自刀骗药或做身份；狼人夜聊必须给出刀口与次日公开策略，白天发言需与自身公开叙事和夜间制定的公开战术方向自洽但不得泄露夜聊；女巫首夜默认救但不无脑，银水不等于铁好，刀口明显像自刀或留解药能逼狼刀时可跳过；女巫只能在自己的私有用药记录支持时确定说明药量，不得把未公开死因强行归因为毒药、解药、狼刀或守卫挡刀；守卫按轮次守人，明预可信也不能机械连续守同一人；预言家、村民和投票围绕查验链、发言矛盾、票型和强推可信好人的行为站边。`DAY_VOTE` / `DAY_VOTE_PK` 仍按规则允许普通自投，但 prompt 必须要求默认不要自投，只有做身份、救队友、自救或保护可信好人等公开收益极高时才考虑自投。`v5` 不改变输出 JSON schema、事件 schema、PlayerView payload 字段、fallback、ack、EventLog、replay hash 或 resimulate 语义。`DAY_SPEECH` / `NIGHT_WOLF_CHAT` 的模型正常输出若为空、纯占位或直接为 `[沉默]`，按 schema violation 进入重试与 fallback，只有 fallback 路径可生成 `[沉默]`。`JSON payload` 只包含 seat、role、phase、rule_set_summary、teammates、Referee 过滤后的 visible_events、由 visible_events 纯函数派生的 speech_context、output_schema，以及仅 wolf 夜聊/狼刀阶段允许出现的 `wolf_private_context`。`rule_set_summary` 必须包含公开投票规则 `vote_sheriff` 与 `can_abstain`，当前 `vote_sheriff` 固定为 `false`，供提示词明确禁用警长、警徽、警上警下和警长归票机制；`can_abstain` 控制 `DAY_VOTE` / `DAY_VOTE_PK` 是否允许输出 `target: null` 弃票。`DAY_SPEECH`、`DAY_VOTE`、`DAY_VOTE_PK`、`NIGHT_WOLF_CHAT` 与 `NIGHT_WOLF_VOTE` 的公开发言集中进入 `speech_context`，`visible_events` 不重复携带大量 `speech` 事件。`speech_context` 固定包含 `current_seat`、`already_spoken_seats`、`not_yet_spoken_seats`、`own_public_speeches`、`prior_public_speeches`，其中 `not_yet_spoken_seats` 仅表示当前白天仍未轮到或尚未完成公开发言的存活座位，不得被解释为沉默、划水、不活跃或藏身份。`speech_context` 不得引入未经过 Referee 过滤的事件、昵称、provider、raw response 或私有信息。LLM 重试时只在末尾追加结构化错误说明。

`v5` 顺序发言补充：所有角色的 `DAY_SPEECH` prompt 必须说明只能评价已经出现在 `speech_context.prior_public_speeches` 的公开发言；`not_yet_spoken_seats` 只表示尚未轮到，不能作为不报查验、未回应、沉默、划水、不活跃、发言少或藏身份的证据。`DAY_VOTE` / `DAY_VOTE_PK` prompt 只能把已经完成的公开发言、公开票型、夜晚公示和可见查验链作为投票依据，不得把后置位未发言作为投票理由。判断预言家是否报查验，只能基于该座位已经公开发言后的文本。

`v5` 守卫白天策略补充：守卫低收益时不主动跳身份；但在公开发言、公开票型或 PK 局势显示自己高概率被误放逐时，应明牌守卫自救，并给出可公开、可验证的关键守护线索。该补充只改变 prompt 策略文本，不改变输出 JSON schema、事件 schema、PlayerView payload 字段、fallback、ack、replay 或 resimulate 语义。

输入侧：

- Referee 不做开放式语义审查。
- Referee 只保证注入 prompt 的私有信息正确脱敏，并对输出文本执行确定性事实一致性 hook。
- 发言中声称拥有不存在的信息属于合法角色扮演；但不得输出可由规则和本人可见历史确定为不可能或越权的事实。
- 文本事实一致性 hook 至少覆盖：守卫不得声称连续两晚守同一人；守卫不得把“守护成功/挡刀成功”说成确定事实；任意玩家不得引用未授权狼聊、狼刀目标、provider、model name、raw response 或事件 schema 名作为可见事实；玩家不得在公开夜晚结果前确定声称平安夜或夜晚死亡；非女巫不得确定声称女巫毒药状态；任意玩家不得仅凭公开双死把毒药参与或药量状态说成确定事实。
- 泄漏测试覆盖预言家结果、狼队身份、狼刀细节、守卫目标、`last_guard_target`、女巫用药、狼刀目标和药品剩余状态。

输出侧：

- 所有 LLM 输出走结构化 schema 校验。
- Schema 校验通过后必须进入 Referee 行动合法性校验；`DAY_SPEECH` / `DAY_LAST_WORDS` 还必须进入文本事实一致性 hook。任何失败都按 §11 重试与 fallback 处理。
- 输出 JSON schema 按 phase 固定为：`NIGHT_GUARD {target}`、`NIGHT_WOLF_CHAT {text}`、`NIGHT_WOLF_VOTE {target}`、`NIGHT_WITCH {action, target?}`、`NIGHT_SEER {target}`、`DAY_SPEECH {text}`、`DAY_VOTE {target: int | null}`、`DAY_VOTE_PK {target: int | null}`、`DAY_LAST_WORDS {text}`。

PlayerView 大小控制 / 上下文管理策略：

- Prompt 上下文只从 Referee 过滤后的 `PlayerView.visible_events` 构造。
- `speech_context` 只从同一份 `PlayerView.visible_events` 派生，不写入 EventLog，不改变 replay hash，不作为行动合法性来源。
- 默认使用最近 40 条事件，并强制保留 `game_start`、`death_at_night`、`exile`、`witch_action`、`seer_check_result`。
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
- `src/wolven_hunt/llm`：LiteLLM 网关、structured output、阶段级重试/超时、fallback、成本记录。
- `src/wolven_hunt/storage`：事件日志、快照、两种 replay 模式。
- `src/wolven_hunt/api`：FastAPI 控制接口，STEP-06 实现。

落盘目录固定为 `runs/{game_id}/events.jsonl`、`raw_responses.jsonl`、`manifest.json`、`cost.jsonl`、`narrative.jsonl`、`final_reveal.json`、`review_report.json`。`review_report.json` 是赛后 AI 复盘报告，只能从 Referee 过滤后的 spectator events、`narrative.jsonl`、`final_reveal.json` 与 manifest 中的 `seat_presentation` 派生，不进入 EventLog、PlayerView、narrative、SSE、玩家行动 prompt、replay hash 或 resimulate 校验。STEP-08 起复盘报告 schema 为 `1.1`，包含 `generation_mode: real_ai | offline_mock`、summary、leaderboard、players、key_decisions、counterfactuals；leaderboard 的 `reason` 字段用于一段式概括该模型/玩家本局整体表现，必须覆盖角色、关键公开证据、排名原因和短板，不再只放单条证据或短排序理由；players 使用六边形评分 `scores: [{key, label, value}]`，六轴固定为发言质量、推理逻辑、票型执行、阵营贡献、信息控制、角色职责，其中角色职责按身份显示为狼队协同、查验价值、药水决策、守护判断或平民职责。真实赛后评审 provider 使用两阶段 pipeline：先加载 `configs/prompts/zh/review/global.v1.md` 生成 summary、key_decisions、counterfactuals，再由 Python 侧为每个座位构造 `PerSeatDossier` 并并发加载 `configs/prompts/zh/review/per_seat.v1.md` 生成单玩家评分、证据、建议和 leaderboard reason，最后由 Python 组装并用 `ReviewReportModel` 校验完整 schema；旧 `configs/prompts/zh/review/report.v1.md` 与 `build_review_prompt` 仅作为旧测试/兼容路径保留。dossier 与 prompt 输入只能使用 spectator events、narrative rows、role reveal 与 `seat_presentation`，不得读取 raw response、provider、API key、玩家行动 prompt 原文或未授权私有事件；每名玩家评价必须引用独有公开证据，优先覆盖发言、票型、死亡/存活节点和角色职责，禁止无事实支撑地复用泛化优缺点或建议；`key_decisions` 必须围绕影响胜负或阵营结构的公开节点写清发生了什么、为什么关键、对胜负的影响，内部 `actors_involved` 只用于生成 per-seat dossier，组装出口前必须剥离；`counterfactuals` 必须基于关键决策推演公开选择改变后的可能局势与下一局启发，不得引入未公开私有行动。真实 review provider 的报告级降级策略固定为：global stage 失败时整体返回 `build_mock_review_report` 的 `offline_mock` 报告；per-seat stage 单个座位失败时仅该座位使用 mock player row 兜底，其余座位仍使用真实输出并保持本次报告的 `generation_mode`。修改 review prompt 或 review pipeline 不改变报告 schema、已有 v1.1 缓存策略、EventLog、PlayerView、narrative、SSE、玩家行动 fallback、ack、replay hash 或 resimulate。旧版 `1.0` 报告视为过期缓存，`GET` 按未生成处理，`POST` 可重新生成并覆盖。`manifest.json` 可记录 spectator-safe 的 `seat_presentation` 展示快照，仅包含本地 UI 昵称与 `/assets/lobby/` 头像路径，不得包含 provider、model name、base URL、API key、raw response、prompt 或私有行动结果；该字段不写入 EventLog，不影响 replay hash 或 resimulate。写入使用 tmp + fsync + atomic rename 或行级 fsync，文件权限为 `0600`。

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

FastAPI 在 STEP-06 实现，所有读取接口默认返回 Referee 过滤后的 spectator 视角。STEP-07 spectator 为观众上帝视角：可包含完整身份表、狼人夜聊和 spectator-only effects，但不包含 raw response、provider 配置、守卫/预言家/女巫私有事件原文或狼刀投票/决定事件原文。

- `POST /games`，可选 `seat_presentation: Record<seat, {nickname, icon_path}>`，仅写入 manifest 作为 spectator-safe UI 展示快照
- `GET /games`
- `GET /games/{id}`，返回 `seat_presentation`；旧 run 没有该字段时返回空对象
- `GET /games/{id}/events`
- `POST /games/{id}/run`
- `POST /games/{id}/pause`
- `POST /games/{id}/resume`
- `POST /games/{id}/replay`
- `POST /games/{id}/dev/inject`
- `GET /games/{id}/stream`
- `GET /games/{id}/narrative`
- `GET /games/{id}/effects`
- `GET /games/{id}/reveal`
- `GET /games/{id}/review-report`
- `POST /games/{id}/review-report`
- `POST /games/{id}/ack`
- `POST /games/{id}/speech`
- `POST /games/{id}/wolf_chat`
- `POST /models/test`

错误体统一为 `{code, message, details?}`。`GET /games/{id}/review-report` 只返回已生成且 schema 有效的 `review_report.json`，未生成或缓存为旧版 `1.0` 时返回 `404 report_not_generated`；`POST /games/{id}/review-report` 只允许 finished game，已有 v1.1 报告时返回缓存，否则调用专用 review provider 生成结构化报告。报告 schema 至少包含 summary、leaderboard、players、key_decisions、counterfactuals，其中 players 必须提供六轴 `scores`、`overall_score`、`evaluation`、`evidence` 与建议；村民的角色职责轴不得显示为技能。真实报告生成固定加载 `configs/prompts/zh/review/global.v1.md` 和 `configs/prompts/zh/review/per_seat.v1.md`，prompt 输入只允许 spectator events、narrative rows、role reveal、seat_presentation 及其纯函数 dossier 派生物，不得读取 `raw_responses.jsonl`、provider 配置、API key、玩家行动 prompt 原文或未授权私有行动结果；模板缺失不得回退到弱提示词，而是按 global stage 失败策略返回明确标记的 `offline_mock` 报告。真实 review provider 配置存在时必须调用真实 provider 的两阶段 pipeline，未配置时允许生成明确标记的 `offline_mock` 离线复盘；真实 provider 的 global stage 失败时返回 `offline_mock` 报告，per-seat stage 单座位失败时仅该座位 mock 兜底，报告生成不得改变 EventLog、replay hash、SSE 或历史列表。`speech` 与 `wolf_chat` 端点仍走 Referee `validate_action`，前端不得自行绕过合法性校验。`POST /models/test` 只做临时连通性测试，请求允许携带 `thinking_enabled`，未携带时默认为 `false`；正式游戏的 `AgentSpecLLM` 同样允许携带 `thinking_enabled`。Qwen 系列必须把 `thinking_enabled` 显式映射为 provider 请求中的 `enable_thinking: true/false`，其他模型仅在 `true` 时追加 provider 兼容的 thinking 参数。OpenAI-compatible provider 若明确拒绝非流式请求并要求 `stream`，后端可用同一请求参数自动重试 `stream: true` 并聚合 delta 文本。前端模型连通性测试失败后按 `1s → 3s → 5s → 10s` 自动重测；该重测只重复临时 `/models/test` 调用，不写入 EventLog、runs、raw response、cost、narrative、manifest 或 SSE。`thinking_enabled` 与 stream 兼容重试仅用于 provider 调用参数，不进入 EventLog、PlayerView、narrative、spectator API、manifest 或 SSE，不影响 replay hash。不写 EventLog、不落盘、不返回 API key；失败响应只返回脱敏后的短错误摘要。所有模型 provider 调用必须直连，不继承系统 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` / `NO_PROXY`；LiteLLM 导入阶段和请求阶段都必须禁用环境代理，不通过安装 SOCKS 依赖来兜底。

SSE 线协议固定为 `event: game_event`、`id: <seq>`、`data: <spectator Event JSON>`；STEP-07 额外推送同源 `event: narrative_row` 与 `event: spectator_effect`，三类事件共享原始 EventLog `seq`。live SSE cursor 按已完成 spectator/narrative/effect 投影发布的 raw seq 推进；每条 raw event 独立决定是否产生 filtered `game_event`、`narrative_row`、`spectator_effect`，但服务端只有在该 raw event 的所有投影都写入 session 后才允许 SSE 消费该 seq。服务端可在 SSE 建立时先发送 `event: stream_ready` 控制帧用于解除前端启动握手等待；该帧不带 `id`，不对应 EventLog 事件，不推进 cursor，不进入 narrative、spectator projection、manifest、replay/resimulate 或 replay hash。每 30s 发送 `event: heartbeat`。`Last-Event-ID` 表示从 `seq + 1` 续推，不存在则返回 410。STEP-08 起前端默认同源相对路径；开发模式 Vite `7001` proxy 到 FastAPI `7002`，生产模式 FastAPI `7002` 服务 `dist/` 和 API。

STEP-06 环境变量统一由 `src/wolven_hunt/config/settings.py` 的 `pydantic-settings.BaseSettings` 读取：

- `WH_LLM_PROVIDER`：`mock` | `litellm`，缺省为 `mock`；非法值启动失败
- `WH_LLM_API_KEY`：真实 provider 的 API key；`WH_LLM_PROVIDER=litellm` 时必填
- `WH_LLM_BASE_URL`：LiteLLM base URL，可选
- `WH_LLM_MODEL`：默认模型名，可选
- `WH_LLM_TIMEOUT_SECONDS`：单次调用超时，默认 30
- `WH_LLM_MAX_RETRIES`：重试预算，默认 4；已加载 RuleSet 的 `fallback.max_retries` 优先
- `WH_LLM_BUDGET_PER_GAME`：单局 token 上限，默认 100000；超限时发一次 `agent_budget_warning`，游戏继续运行
- `WH_LLM_PROVIDER_MAP`：空字符串或 YAML 路径；非空时按座位路由 provider，缺失座位回退到全局 `WH_LLM_*`
- `WH_REVIEW_PROVIDER`：赛后 AI 复盘报告 provider，`mock | litellm`，默认 `mock`；`litellm` 生成 `generation_mode=real_ai`，`mock` 生成 `generation_mode=offline_mock`
- `WH_REVIEW_API_KEY`：赛后报告真实 provider 的 API key；仅 `WH_REVIEW_PROVIDER=litellm` 且触发报告生成时需要，缺失时生成失败但不得静默降级为 mock
- `WH_REVIEW_BASE_URL`：赛后报告 LiteLLM base URL，默认 `https://yunwu.ai/v1`
- `WH_REVIEW_MODEL`：赛后报告模型名，默认 `gpt-5.5`
- `WH_REVIEW_TIMEOUT_SECONDS`：赛后报告单次调用超时，默认 60
- 真实赛后复盘 provider 调用默认开启 thinking 语义；当 `WH_REVIEW_MODEL` 为 `gpt*`（含默认 `gpt-5.5`）时，LiteLLM 请求必须传顶层 `reasoning_effort: "xhigh"`，作为复盘总结的最高思考档位。该参数只影响 review-report 生成质量/耗时，不进入 EventLog、PlayerView、narrative、SSE、manifest、replay hash 或 resimulate。
- `WH_PACING_PROFILE`：`live | fast | off`，默认 `live`；CI / replay / resimulate 强制 `off`
- `WH_PACING_PHASE_MS`：phase 切换基础停顿，默认 600
- `WH_PACING_SPEECH_MS`：speech / wolf_chat / last_words 后停顿，默认 400
- `WH_PACING_NIGHT_MS`：进入夜晚的额外停顿，默认 1000
- `WH_PACING_ACK_TIMEOUT_MS`：现场观赛 ack 最大等待时间，默认 15000；ack 超时只解除等待，不写 EventLog
- `WH_RUNS_DIR`：落盘根目录，默认 `./runs`
- `WH_API_HOST`：FastAPI 监听地址，默认 `127.0.0.1`
- `WH_API_PORT`：FastAPI 监听端口，STEP-08 起默认 7002
- `WH_API_CORS_ORIGINS`：CORS 白名单，逗号分隔，STEP-08 起默认 `http://localhost:7001`
- `WH_SERVE_STATIC`：生产模式是否由 FastAPI 同源服务 `dist/`，默认 `false`

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
- 狼严格人数优势、村民边全灭、神职边全灭、狼全灭和每个检查点。
- 首夜狼刀/双奶死亡遗言、首夜毒药死亡无遗言、第二夜后夜死无遗言、守卫平安夜、女巫救人、女巫毒人、双奶死亡、同夜双死、PK、二次平票。
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

STEP-07 新增 `PacingController`，由运行时在事件发布后调用；`profile=off` 时为 no-op。现场观赛 audio/video 与 transient spectator effects 通过 `POST /games/{id}/ack` 解除等待；effect ack event 名称固定为 `spectator_effect_rendered:<seq>`。ack 不进入 EventLog、不影响 replay hash，超时只解除等待。

## 17.1.1 Spectator-only Effects

STEP-07 新增观赛特效投影 `SpectatorEffect`，它从完整 EventLog 派生，不是 EventLog 事件类型，不进入 PlayerView、prompt、narrative 或 replay hash。schema 固定为 `{seq, day, phase, kind, actor, source_seat, target_seat, asset_key, duration_ms, meta}`，`kind` 固定为 `guard_shield | wolf_attack | seer_vision | witch_potion | death_reveal`。

- `guard_protect` 派生 `guard_shield`，只给 spectator effects 展示目标护盾。
- `wolf_kill_decided` 派生 `wolf_attack`；如果同夜守卫目标等于狼刀目标，`meta.blocked_by_guard=true`，前端在 3 秒内淡出。
- `seer_check` 派生 `seer_vision`，只展示查验目标，不展示 `seer_check_result` 的阵营结果。
- `witch_action(save|poison)` 派生 `witch_potion`，从女巫座位飞向目标座位；`skip` 不派生特效。
- `day_announce` 中的死亡列表派生 `death_reveal`，前端在白天公布后再灰化头像。

`guard_shield`、`wolf_attack`、`seer_vision`、`witch_potion` 是现场观赛 transient effects，只能在非终局阶段播放；live pacing 中它们是动作完成后的可见节奏点，后端发布对应投影后可等待前端 `spectator_effect_rendered:<seq>` ack 或超时，再推进下一阶段。前端必须在座位叠层/药水动画挂载并短暂可见后再发送该 ack；若资源加载失败、浏览器禁用动画、页面重连或静音/自动播放限制导致无法完成真实播放，前端必须在本地超时内发送 fallback ack，后端也必须按 `WH_PACING_ACK_TIMEOUT_MS` 超时继续。前端新建观赛对局必须显式使用 `live` pacing，并采用 `点击夜深了后立即进入游戏现场 -> start_paused=true 创建后端对局 -> 建立 SSE -> 最小现场壳挂载完成 -> POST /run` 的启动握手，确保首个夜晚现场 effect 不会在前端订阅前被写成历史；游戏音频、特效图片和其他静态资源只允许 best-effort lazy preload，不得阻塞进入游戏现场或 `/run`。SSE 中收到的 live transient effect 是现场座位叠层动画的唯一触发来源，REST narrative/effects 回补只能更新历史 UI 状态，不得推进 `Last-Event-ID` cursor、不得清空或过期正在播放的 live transient effect，也不得吞掉后续同 seq live effect；narrative-only 回调不得把 cursor 推过同 seq 尚未消费的 `spectator_effect`。live SSE cursor 必须以“已发布投影”的 raw seq 为准；服务端不得让客户端 cursor 越过尚未发布 `spectator_effect` 的 private action seq。进行中的 live 观赛对局允许写入 UI-only `localStorage` 快照，用于刷新、HMR 或页面重载后恢复 `gameId`、席位分配、`seat_presentation`、启动状态、SSE raw cursor、effects cursor 与尚在可见窗口内的 recent transient effect queue，并重新订阅 SSE；该快照必须在退出、终局或复盘入口清理，不进入 EventLog、manifest、narrative、SSE、replay/resimulate 或 Referee/RuleEngine 边界。进入 `GAME_END` / `role_reveal` 后前端必须抑制并清空这类未完成动效，不得集中补播积压特效。复盘或 REST 回补中已发生的非死亡 transient effects 默认视为历史并标记为过期；`death_reveal` / `out_badge` 和 `role_reveal` 仍可在终局保留。

`GET /games/{id}/effects?after=<seq>` 返回 spectator-only effects。SSE 使用 `event: spectator_effect` 推送同一投影；这不允许前端绕过 Referee 获取可用于玩家决策的私有事件原文。

## 17.2 STEP-08 Playable Distribution

STEP-08 目标是 10 个 AI 自动对局从前端开局后可无卡点观赛到终局，不实现真人入座或多人房间。

- 部署拓扑：dev 使用 Vite `7001` + proxy，prod 使用 FastAPI `7002` 挂载 `dist/` 静态文件；前端 API base 默认空字符串，即同源相对路径。
- 历史复盘：`GET /games` 从 `runs/` 读取 manifest 汇总；`GET /games/{id}/events` 在线返回 session spectator events，离线从 `events.jsonl` 读取并按 spectator 过滤。不得读取或暴露 `raw_responses.jsonl`，但可保留身份表、狼人夜聊和 `seat_presentation` 供观众复盘。
- `seat_presentation` 是纯 UI 展示元数据，只用于历史复盘恢复游玩时头像和昵称；它不改变身份来源、胜负判定、行动合法性、ack、EventLog、replay hash、resimulate 或 LLM 输入。
- 游戏结束后的前端结算使用“终局定格态 + 可展开复盘抽屉”：默认保留原游戏舞台、座位、聊天框、投票直方图、身份徽标和出局标记，只叠加极简胜负与操作控件；详细复盘默认收起，只展示 `role_reveal.highlights` 和 spectator-safe 身份全览，不直接暴露 raw event JSON。终局定格态不得继续播放或补播 `guard_shield`、`wolf_attack`、`seer_vision`、`witch_potion` transient spectator effects。
- 终局定格态复盘入口在 STEP-08 起改为「生成复盘报告」；生成中必须禁用灰态并显示 spinner 与「正在生成中」，成功后改为「查阅报告」。报告抽屉展示战局摘要、生成模式标识、Leaderboard/排行榜、每名玩家角色感知六边形评分、具体评语与公开证据、关键决策复盘、反事实推演和建议；不得展示 game id、schema、generated_at、provider、model name、API key、raw response 或 prompt。大厅「历史复盘」入口和历史列表内「复盘」按钮保持原行为与文案。
- replay 恢复：STEP-08 起 manifest 必须写入 `config_path` 与 `prompt_pack_version`；`replay_resimulate` 在未显式传入 config 时从同目录 manifest 恢复配置和 prompt 版本。缺失 `config_path` 时只能按 8 人 seat_range 回退 classic_8；缺失 `prompt_pack_version` 时回退当前默认 prompt `v5`。旧玩家 prompt `v1` / `v2` / `v3` / `v4` 已移出主仓库，不再作为本地 resimulate 兼容输入；新 run 默认使用 classic_10 与 prompt `v5`。
- 前端健壮性：SSE 客户端必须使用 `Last-Event-ID` 断点续传，最多 4 次固定延迟重连，延迟序列为 `1s → 3s → 5s → 10s`，不使用 jitter；失败后显示错误状态。REST 回补不得更新 raw event cursor，cursor 只能由 SSE raw event id 推进。倒计时归零后显示等待状态，避免误判为卡死。
- 模型测试：前端只调用后端 `POST /models/test`；测试失败后前端按固定序列 `1s → 3s → 5s → 10s` 自动重测，任一尝试成功即视为通过；测试失败不能永久阻止开始游戏，用户可继续开局，运行期由 LLM 重试和 fallback 保证收敛。
- 模型联网：正式对局 LLM 调用、`POST /models/test` 与真实 LLM smoke test 均强制直连，忽略系统代理环境变量。
- 文档与 CI：默认 CI 使用 mock provider；真实 LLM smoke 必须通过环境变量显式开启。默认前端模型 key 保留为作者轮换 key 策略，用户 localStorage 覆盖优先。

## 18. Web Shell Boundary

本节是 `plan.md` §14「前端入口骨架（Web Lobby Shell）」的契约落地。前端壳与 Python 引擎在同一仓库共存，但权限边界、数据流与命名空间必须严格切开。

### 18.1 模块边界

- 前端入口壳的源码位于仓库根目录：`package.json`、`package-lock.json`、`index.html`、`vite.config.ts`、`tsconfig.json`、`tsconfig.node.json`、`src/components/`、`src/hooks/`、`src/main.tsx`、`src/App.tsx`、`src/styles.css`、`public/`。
- 与 `src/wolven_hunt/*` 双向不导入：前端不得引用 `src/wolven_hunt/*` 或 `configs/*`；Python 引擎不得依赖前端代码。
- 前端只消费 Referee 过滤后的 spectator 视角。STEP-07 观众页可展示全部身份与狼人夜聊；任何玩家视角、行动校验、raw response、provider 配置、守卫/预言家私有事件和狼刀细节均通过 §15 FastAPI 边界控制；前端**不得绕过 Referee**。
- 第一阶段大厅页**没有任何后端调用**：纯静态资源 + UI 状态，不发起 HTTP / WebSocket / SSE 请求。

### 18.2 前端栈

- Vite + React 18 + TypeScript。
- 使用 npm 管理依赖，`package-lock.json` 必须随 `package.json` 提交以保证安装可复现。
- 图标使用 `lucide-react`。
- 不引入额外的 CSS 框架；不引入路由库（按钮 click 仅 stub）。

### 18.3 静态资源命名与构建

- 运行时资源放在 `public/assets/lobby/` 与 `public/assets/game/`，文件名 ASCII 小写蛇形：`lobby_pingpong.mp4`、`lobby_bgm.mp3`、`lobby_poster.jpg`、`btn_start.png`、`btn_history.png`、`btn_settings.png`、`settings_panel_bg.png`、`model_icon_minimax_laoshi.png`、`model_icon_wanwen.png`、`model_icon_guangzhimingmian.png`、`model_icon_dami.png`、`model_icon_xueba.png`、`model_icon_xiaodoubao.png`、`model_icon_haiseyin.png`、`model_icon_gemini.png`（源自 `素材/Gemini.png`）、`quick_assign_raccoon.png`（运行时资产直接提交）。
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

### 18.8 历史阶段交付规格归档

当前权威契约只保留在 `plan.md` 与 `architecture.md`。历史阶段执行规格、验收截图和废案计划已归档到 `/Users/tampouseng/Desktop/Wolven Hunt 废案/2026-05-29-repo-cleanup/docs/`，不再参与运行时、测试、构建或后续实现决策。

### 18.9 大厅弹窗层（Lobby Modal Layer）

- 大厅三个按钮（开始游戏 / 历史复盘 / 系统设置）共用通用弹窗外壳 `LobbyModal`，按 kind 切换内容（StartModal / HistoryModal / SettingsModal），同一时刻最多打开一个弹窗。
- 弹窗状态 `activeModal: 'start' | 'history' | 'settings' | null` 存放在 `LobbyHome`；`LobbyButtons.onAction(kind)` 直接 `setActiveModal(kind)`。
- 弹窗背景固定为 `public/assets/lobby/settings_panel_bg.png`；弹窗主体通过 `createPortal` 挂载到 `document.body`。
- 关闭方式三选一：右上角 `<X />` 按钮、`Esc` 键、点击遮罩区。三种都调用 `onClose`。
- 打开时焦点进入弹窗，关闭时还原焦点；`role="dialog"`、`aria-modal="true"`、`aria-labelledby` 指向标题元素。
- 弹窗层 z-index 高于 lobby 视频 / shade / 按钮 / mute toggle，但仍属于前端壳，**不发起任何网络请求**（与 §18.1 / §18.7 一致）。

### 18.10 模型配置存储（Model Configs）

- 系统设置弹窗内含 10 个模型 slot。每个 slot 由两部分组成：
  - **静态部分**（不进 `localStorage`）：`slot` 索引、中文 `nickname`、ASCII `iconPath`，统一定义在 `src/lib/modelConfigs.ts` 的 `MODEL_SLOTS` 常量数组。
  - **默认模型输入部分**：`baseUrl` / `apiKey` / `modelName` / `thinkingEnabled`，统一定义在 `src/lib/modelConfigs.ts` 的 `MODEL_CONFIG_DEFAULTS`，用于预填系统设置；10 个默认 slot 的 `thinkingEnabled` 固定为 `false`。
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
- 进入游戏触发时同步调用 `useLobbyAudio.pauseForGame()` 暂停 BGM，但不写入 `wolven_hunt.lobby.muted`；audio store 是模块级单例，lobby 卸载后播放状态保留。不新增 fadeOut ramp API；如需平滑淡出留给后续步骤。游戏页阶段语音由独立 `gameAudio` 控制，使用右上角游戏语音开关与 `wolven_hunt.game.*` 本地状态。
- 游戏准备页 `<GamePage />`：白天背景图（`/assets/game/day_bg.png`）`object-fit: cover` 全屏；席位区分左右两列，左列 1–5、右列 6–10 垂直 flex 居中分布。
- 席位组件 `<GameSeat />` 两态：
  - 空态：圆形虚线边框 + lucide `Plus` 图标；点击触发 `ModelPicker` 弹窗。
  - 已分配态：圆形模型头像 + 外侧加粗昵称文字；点击头像同样触发 picker，可重新选择。昵称需带增强文字阴影，避免白天背景下可读性不足。
- 席位编号是 `<GameSeat />` 的纯 UI 徽标：基于 `seatIndex + 1` 显示 1–10，左列编号位于圆圈左下角，右列编号位于圆圈右下角；编号不写入 `assignments`，也不进入 Referee / FSM / RuleEngine 边界。
- 模型选择 `<ModelPicker />`：使用游戏页自有弹窗外壳（不复用大厅 `LobbyModal` 或 `settings_panel_bg.png`），渲染 `MODEL_SLOTS` 10 张卡片网格；已被其他席位占用的卡片主体 `disabled` + 灰度滤镜，但卡片右下角保留图标型「交换」按钮，用于把当前席位模型与该模型所在席位互换。当前席位已选卡片黄色边框高亮。
- 分配状态 `assignments: (number | null)[]`（长度 10）保存在 `<GamePage />` 内部 state；未开局准备态不写 `localStorage`，刷新页面恢复初态。点击「夜深了...」创建 live 观赛对局后，可按 §17.1.1 写入进行中对局恢复快照；退出或终局后必须清理。每个 model slot 在 10 席位中至多出现一次。
- 模型交换只调换 `assignments` 中两个 seat index 的 slot 值，不写 `localStorage` / 事件日志 / replay，不触发 Referee / FSM / RuleEngine，也不清空按 model slot 记录的 `testResults`；测试徽标随模型头像移动。
- 「一键分配」是游戏准备页的纯 UI 快捷操作：入口位于左下角，由 `quick_assign_raccoon.png` 装饰图与按钮组成；点击后用 Fisher-Yates 洗牌 `MODEL_SLOTS` 的 0–9 索引并一次性写入 `assignments`。该随机不写事件日志、不参与 replay、不进入 Referee / FSM / RuleEngine；触发后必须清空旧 `testResults` 与测试提示，避免旧连通性标记误用于新席位。
- 席位身份占位 `.game-seat-role` 本步骤 `display: none`，作为 `身份分配 / 标识展示` 的扩展点，**不进入** Referee 边界；后续与游戏阶段同步显示分配结果时仍由 Referee 提供脱敏视角，不绕过 §18.1 单一权限边界。
- 游戏准备页**不发起任何网络请求**、**不引入游戏逻辑**、**不读取 `wolven_hunt/*` 模块**，与 §18.1 / §18.7 / §18.9 同等边界一致。
- 游戏准备页复用 `MODEL_SLOTS` 头像与昵称；模型 API 默认值只用于系统设置弹窗预填，不在本步骤用于席位分配或网络调用。

### 18.13 游戏内 UI 增强（Game Page Enhancements）

本节是 STEP-04 的架构契约，与 `plan.md` §14.14 一致。在 §18.12 基础上叠加：

- **`App.tsx` 双向页面切换**：新增 `targetPageRef: useRef<Page | null>` 记录 fade-out 后的目标页；`handleEnterGame` 设 `targetPageRef.current = 'game'` + `phase = 'fade-out'`，`handleExitGame` 设 `targetPageRef.current = 'lobby'` + `phase = 'fade-out'`。`onTransitionEnd` 在 fade-out 结束时读 `targetPageRef.current` 切页面 + 下一帧切 fade-in。退出时不自动还原 BGM 播放状态。
- **GamePage 内部 stage 状态机**：`stage: { dayNumber, phase }` 与 `bgPhase: 'idle' | 'fade-out' | 'fade-in'` 由 GamePage 持有；`pendingStageRef` 临时记录待切换的 stage。`<img class="game-bg" src={...}>` src 由 `stage.phase` 派生。`.game-stage-overlay` 的 z-index = 4，覆盖背景图但低于顶栏（z=5）和模态弹窗（createPortal 到 body）。**不复用** App 层 `.page-transition-overlay`，避免白天↔黑夜与 lobby↔game 切换互相耦合。
- **阶段与布局修正**：`StageIndicator` 显示太阳/月亮 + `第{dayNumber}天`，图标与文案垂直居中。席位昵称显示在头像下方并限制宽度；聊天区位于两列席位之间（当前 `left/right: clamp(118px, 25vw, 220px)`），底部预留操作区空间（当前 `bottom: clamp(200px, 20vh, 260px)`），在约 500px 宽 in-app browser 下也不得与昵称或底部按钮重叠。
- **GameTopBar / StageIndicator / GameChat / GameBottomActions / RulesModal / ExitConfirmModal** 全部位于 `src/components/Game/` 命名空间。`RulesModal` 使用游戏页自有弹窗外壳与滚动正文背景，不复用大厅 `settings_panel_bg.png`，并对 `rules.md` 做轻量 markdown 解析（标题 / 列表 / 加粗）后渲染为结构化正文；`ExitConfirmModal` 使用游戏页自有紧凑确认面板，不复用大厅竖版背景图；游戏页跨命名空间复用仅限通用 UI 外壳与 `MODEL_SLOTS` 静态配置。
- **席位测试态边界**：`<GameSeat testStatus>` 仅是 UI hint，不进入 Referee / FSM / RuleEngine；testStatus 由 GamePage 派生自 `testResults[assignment]`。`readModelConfig(slot)` 优先读取 `localStorage` 用户覆盖；没有用户覆盖时使用 `MODEL_CONFIG_DEFAULTS[slot]`，仅当有效 `baseUrl` / `apiKey` / `modelName` 缺失时返回 `null`，并兼容旧缓存的 `thinkingEnabled` 默认回退。`testResults` 与测试状态提示不写 `localStorage`，刷新或退出大厅再进入即重置。改 assignments 时清除被覆盖 slot 的 testResult。测试中按钮文案显示为「正在测试中」，并至少展示一次可感知的 loading 态；测试完成后每个已分配 slot 必须落成 `pass` 或 `fail`，底部显示通过数量摘要；失败时展示模型昵称与后端返回的脱敏短错误。单个 slot 的连通性测试失败后自动按 `1s → 3s → 5s → 10s` 重测，任一尝试成功即落成 `pass`，全部失败才落成 `fail`；取消信号触发后必须立即返回“已取消”，不得继续排队重试。GamePage 可在本轮测试内为每个 slot 记录 UI-only 墙钟耗时（开始偏移、结束偏移、总耗时）并展示按耗时降序排列的诊断表，第一行标记最慢模型；这些 timing diagnostics 仅保留在当前前端内存，不进入 `localStorage`、Referee / FSM / RuleEngine、EventLog、`runs/`、raw response、narrative、SSE、manifest 或 replay hash，也不得包含 API key、provider raw response 或后端私有响应。
- **网络请求边界（§18.1 / §18.7 豁免登记）**：STEP-04 首次允许前端代码出现 `fetch()`，仅在以下两类受限场景：
  - **同源静态资源 fetch**（`/assets/game/rules.md`）：等价于 `<img>` / `<video>` 的资源加载，不构成跨域 / 后端 / LLM 调用，不破坏单一权限边界。
  - **用户主动触发的 LLM 配置自检 fetch**（`testModelConnection`）：仅响应"测试模型连通性"按钮点击；前端只向同源后端 `POST /models/test` 发送 `{provider, model, base_url, api_key, timeout_seconds, thinking_enabled}`，后端临时发起 OpenAI 兼容调用。Qwen 系列始终显式传 `enable_thinking: true/false`；其他模型仅当 `thinkingEnabled === true` 时按模型名追加思考模式字段：`gpt*` 传顶层 `reasoning_effort: "xhigh"`；`kimi*` / `mimo*` / `deepseek*` / `glm*` / `doubao*` 用 `thinking: {type: "enabled"}`；`hy3*` 用 `chat_template_kwargs: {thinking: true, reasoning_effort: "medium"}`；`MiniMax*` 用 `reasoning_effort: "medium"`。返回值仅用于 ✓/✗ 视觉反馈与脱敏错误诊断，**不构成 PlayerView**、**不进事件日志**、**不参与胜负判定**。属于工具型调用，与 §18.1 "Referee 唯一权限边界"不冲突——因为它不产生任何游戏状态。
  - 这两类豁免**不允许**扩展到对局推进、聊天消息收发、玩家行动同步等任何 runtime 数据流；引擎数据流必须等 P2 接入 FastAPI 后由 Referee 控制。
  - apiKey 只在前端到本地同源后端的临时请求体中传输；后端不得记录或回显，失败响应必须脱敏。网络/API 失败由用户感知为 ✗ 与短错误，不静默吞错。
- **DEV-only 调试入口**：`import.meta.env.DEV` 守卫的 [debug] 推进按钮仅供开发期预览白天/黑夜切换；生产 Vite 构建会 tree-shake；不进入交付路径。
