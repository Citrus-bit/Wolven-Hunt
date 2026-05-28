# Wolven Hunt 首期架构骨架修订计划 v4

## Summary

- 默认固定 10 人板：**3 狼人 + 4 村民 + 1 预言家 + 1 女巫 + 1 守卫**。
- 胜负条件：
  - **狼人胜**：`alive_wolves > alive_good_players`（严格大于），或 `alive_villagers == 0` / `alive_gods == 0`（屠边）。
  - **好人胜**：`alive_wolves == 0`。
- 预言家规则：每晚查验一名玩家（**可查死人**，**不可查自己**），只返回阵营（`wolf` / `good`），不返回具体角色。
- 白天被投票放逐的玩家有遗言；首夜可以死亡，**首夜狼刀死亡和双奶死亡的玩家**在首日白天有遗言；毒药导致的死亡任何情况下无遗言，后续夜晚死亡玩家无遗言。
- 女巫每晚在狼人之后、预言家之前行动；每局一瓶解药、一瓶毒药，每晚最多使用一瓶药。
- 投票只能投存活玩家，允许投自己；PK 重投只能投 PK 台上玩家，且 PK 台上玩家不参与重投。
- 编排核心采用**纯 Python FSM 优先**；裁判层（Referee）负责视角隔离与合法性校验；**事件日志是单一事实源**。
- 规则、角色、模型、提示词全部**配置驱动**，核心代码不随板子变化。
- 当前阶段：**STEP-07 / P3 观赛 MVP**。在 STEP-06 外部接入基础上允许实现 per-seat LLM provider 路由、观赛 pacing/ack、叙事化事件流、角色揭晓、前端音视频、倒计时、投票直方图、女巫夜晚行动状态与终局定格态。
- STEP-07 增加 **spectator-only 观赛特效流**：观众上帝视角可以看到护盾、狼袭、预言、女巫药瓶与死亡揭晓动画；普通 PlayerView、prompt、玩家 SSE、narrative 仍不得暴露守卫/预言家/女巫私有结果、狼刀投票细节、provider 配置或 raw response。
- `DAY_SPEECH` / `DAY_LAST_WORDS` 输出必须经过 Referee 文本事实一致性 hook；确定性违反规则机制、本人私有行动历史或越权私有事实的文本按 `illegal_action` 处理，不得进入 EventLog、narrative、spectator API 或 SSE。

---

## 1. 规则契约（Rule Contract）

### 1.1 配置组合

`GameConfig = RolePack + RuleSet + ModelRoster + PromptPack + random_seed`

- 新增板子时只改配置，不改核心代码。
- 每局 `game_start` 记录 `random_seed`、`config_hash`、座位号范围、角色分配结果；回放校验必须使用同一组 metadata。
- `config_hash` 作为 game metadata 进入所有 replay 校验，不要求每条事件重复存储。
- LLM 原始响应只进入私有存储；事件日志只记录 hash 与 storage ref。

### 1.2 默认 RolePack（classic_10）

- 狼人 × 3、村民 × 4、预言家 × 1、女巫 × 1、守卫 × 1。
- 座位统一使用 1-based 编号，默认固定为 1–10 号。
- `GAME_START` 使用 `random_seed` 派生的 deterministic RNG 洗牌分配角色到座位。
- 玩家只知道自己的角色；狼人额外知道全部狼队同伴身份。
- STEP-07 起 spectator 是观众上帝视角：由 Referee 过滤后可看到全部座位身份和狼人夜聊，但仍不得看到 raw response、provider 配置、守卫/预言家私有结果或狼队投刀细节。
- spectator-only effects 是从完整 EventLog 派生的观赛投影，不进入普通 PlayerView 或 prompt，不改变行动合法性、胜负判定、fallback 或 replay/resimulate 语义。

### 1.3 首版 WinCondition

- 每次「夜晚结算」后立即执行胜负检查；「投票放逐」后若有放逐者先执行其遗言，再执行胜负检查。
- 胜负规则按 `RuleSet.win_conditions` 配置驱动执行，默认写入 `majority_or_side_elimination.yaml`。
- 屠边中的神职边固定由好人阵营中非 `villager` 角色组成，当前为预言家、女巫、守卫。

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
- 守卫只影响狼刀，不阻止女巫毒药。

### 1.6 狼人

- 每晚最多 1 轮夜聊（每狼一句），然后**同时**提交刀人目标。`NIGHT_WOLF_CHAT` 必须按存活狼人 seat 升序逐席收集并立即追加 `wolf_chat_message`，后一位狼人通过 Referee 过滤后的狼队视角可看到前序狼聊。`NIGHT_WOLF_VOTE` 可基于同一份夜晚 snapshot 并发收集各狼决策，结算和事件追加仍按 actor seat 升序执行。
- 多数决定刀人目标；平票时**在被狼队投到的目标中随机**选择，并记录 `wolf_tie_random` 事件。
- 合法刀人目标以整轮 `NIGHT_WOLF_VOTE` 为单位校验：狼人可以投任一存活非狼玩家，也可以投自己自刀；`wolves.can_follow_teammate_self_kill: true` 时，若一名狼人本轮也投自己，其他狼人可以跟票该自刀目标。**不允许单方面刀未自投的狼队友，不允许空刀**。
- 狼队夜聊内容对狼队玩家可见；STEP-07 spectator 上帝视角可在狼人聊天框看到真实发言者和内容。

### 1.7 女巫

- 女巫属于好人阵营，每局拥有 1 瓶解药和 1 瓶毒药。
- 女巫每晚在狼人投刀后、预言家查验前行动；女巫死亡后不再行动。
- 女巫知道当晚狼刀目标。解药只能救当晚狼刀目标；毒药可以毒任意存活其他玩家，不能毒自己。
- 每晚最多使用一瓶药，可以选择 `save`、`poison` 或 `skip`；解药和毒药每局各最多使用一次。
- 若守卫守护目标和女巫解药目标同为当晚狼刀目标，则判定为双奶死亡，该目标死亡。
- 守卫不挡毒药。若毒药命中目标，该目标死亡；若毒药目标同时也是狼刀目标，按毒药参与死亡处理。
- 女巫行动生成私有 `witch_action` 事件，仅女巫本人可见；事件记录动作类型和目标，但不得向 spectator 或其他玩家暴露。

### 1.8 发言与投票

- 首夜可以死亡，`rule_set.first_night_can_die: true` 作为首版默认配置。
- 首夜死亡在首日 `DAY_ANNOUNCE` 公示；首夜狼刀死亡和双奶死亡者进入首日 `DAY_LAST_WORDS`，毒药死亡无遗言。
- 白天按座位顺序一轮发言，每名存活玩家一次，中文默认 300 字上限。
- 白天发言和遗言允许正常身份伪装、诈身份和策略性判断；但 Referee 必须拦截确定性不可能或越权的文本事实，例如守卫声称连续两晚守同一人、守卫把“守护成功/挡刀成功”说成确定事实、玩家引用未授权狼聊/狼刀/模型/provider/raw response 作为可见事实。
- 每日 `DAY_SPEECH` 发言起点优先由最近一次夜晚公布死亡决定：若 `state.last_night_deaths` 非空，以其中座位号最大的死亡玩家为锚点，从其下一位存活玩家开始，按座位号递增循环一圈并跳过死亡玩家。若当晚无人死亡，则回退 `rule_set.first_speaker_seat`（默认 1 号）作为起点。
- 投票：同时投票、公开票型、**允许弃票、不允许改票、无警长**。
- `DAY_VOTE` / `DAY_VOTE_PK` 的“同时投票”定义为：所有合法投票者基于同一份 `GameState` 与 `EventLog` 快照独立决策；运行时可并发调用各 Agent，但投票决策在结算前只存在于 FSM 内存 pending action 中，不追加到 EventLog，也不得进入任何 PlayerView、prompt、spectator API 或 narrative。结算时由 Referee 按 actor seat 升序追加公开 `vote_cast`，再追加 `vote_result` / `vote_pk_enter` / `exile` / `peaceful_day`。弃票的 `vote_cast` payload 固定为 `{target: null, abstain: true}`；`vote_result` payload 必须包含 `counts`、`tied`、`abstain_count`、`abstentions`。弃票公开展示但不进入 `counts`，不参与最高票或平票候选；全员弃票直接平安日。EventLog 仍保持 append-only，禁止回写或修改历史 hidden 事件。
- 首轮投票合法目标 = 所有存活玩家，**允许投自己**，不能投已死亡玩家。
- 首轮平票 → 进入 `DAY_VOTE_PK`，平票玩家各一次 PK 发言后重投；如果首轮所有有效票均为弃票，则直接平安日。
- PK 重投合法目标 = PK 台上的存活玩家；PK 台上的玩家不能参与重投。
- PK 重投如果第二次再次平票，或所有台下投票者均弃票，则视为平安日，不放逐任何人，直接进入夜晚。
- 如果 PK 重投时除 PK 台上玩家外无人存活可投，则直接按二次平票/平安日处理并入夜。

### 1.9 遗言

- **有遗言**：白天被放逐者、首夜狼刀死亡者、首夜双奶死亡者。
- **无遗言**：第二夜及之后的夜晚死亡者、任何夜晚被毒药导致死亡者。

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
    → NIGHT_WITCH          # 女巫知道刀口后选择救、毒或跳过
    → NIGHT_SEER           # 预言家查验
    → NIGHT_RESOLVE        # 结算：守、刀、解药、毒药，生成死亡/no_death_tonight 事件
    → CHECK_WIN
  → DAY_ANNOUNCE           # 公示夜晚结果
    → DAY_LAST_WORDS?      # 首日符合条件的夜死遗言；其他夜死跳过
    → DAY_SPEECH           # 按座位顺序发言
    → DAY_VOTE             # 同时投票
    → DAY_VOTE_PK?         # 平票时进入；PK 台下玩家重投
    → DAY_EXILE?           # 有放逐才进入；二次平票平安日则跳过
    → DAY_LAST_WORDS?      # 白天被放逐者遗言；平安日跳过
    → CHECK_WIN
  → 循环回 NIGHT_START
GAME_END
```

STEP-07 live 观赛中，`NIGHT_GUARD`、`NIGHT_WITCH`、`NIGHT_SEER` 是公开夜晚主持与音频 pacing 的固定 phase：只要当前 RolePack 包含对应角色，每晚都必须进入并追加 `phase_enter` / `phase_exit`。若对应神职已死亡，或女巫已无可用药，则该 phase 只用于观赛节奏，不调用死亡/无行动资格 Agent，不生成 `guard_protect`、`witch_action`、`seer_check`、`seer_check_result`、`llm_call`、fallback 或其他私有行动事件。前端收到死亡神职的夜晚 phase 后必须完整播放该神职音频，再固定等待 5 秒后发送对应 ack；ack 仍只控制现场观赛节奏，不写入 EventLog，不影响 replay hash。

### 2.2 结算顺序（NIGHT_RESOLVE）

1. 读取本晚 `guard_protect` 目标 G、狼刀目标 K、女巫动作 W、`seer_check` 目标 S。
2. 若 K 存在且 W 为 `save(K)` 且 G == K，则 K 双奶死亡。
3. 若 K 存在且 W 为 `save(K)` 且 G != K，则 K 存活。
4. 若 K 存在且 W 不是 `save(K)` 且 G == K，则生成 `no_death_tonight`；否则 K 死亡。
5. 若 W 为 `poison(P)`，P 额外死亡；如果 P == K，则死亡只记录一次，并标记为毒药参与死亡。
6. 无死亡时生成 `no_death_tonight`；有死亡时为每个死亡 seat 生成 `death_at_night` 事件。死亡事件不暴露死因。
7. 首夜狼刀死亡和双奶死亡会在首日 `DAY_ANNOUNCE` 公示并触发 `DAY_LAST_WORDS`；毒药导致死亡无遗言；第二夜及之后夜死无遗言。
8. `seer_check_result` 在 `NIGHT_SEER` 时已生成，结算阶段不再处理。

### 2.3 同夜信息可见性

- 狼人**不知道**今晚是否被守（只知道自己投了谁）。
- 女巫只在 `NIGHT_WITCH` 自己的 PlayerView 中看到当晚狼刀目标和药品剩余状态；其他玩家与 spectator 不可见。
- 预言家查验结果在 `NIGHT_SEER` 状态结束时立即对预言家可见（私有事件）。
- 守卫**不知道**自己是否守住了刀（避免反向推理狼队目标）。
- `last_guard_target` 只允许在守卫本人 `NIGHT_GUARD` PlayerView 的 `rule_set_summary` 中出现，用于合法性约束；spectator、非守卫玩家、守卫的非守卫行动阶段均不可见。

### 2.4 首日规则（默认值）

- 首夜：守卫/狼人/女巫/预言家**正常行动**。
- 首夜可以死亡（即 `first_night_can_die: true`）。
- 首日白天：公示首夜死亡结果；如果首夜有人因狼刀或双奶死亡，执行 `DAY_LAST_WORDS`，否则跳过遗言直接进入 `DAY_SPEECH`。
- 首日发言起点遵循 §1.8：有首夜死亡时从最大死亡座位后的下一位存活玩家开始；无死亡时通过 `rule_set.first_speaker_seat` 配置（默认 1 号）开始。

### 2.5 女巫行动规则

- 女巫行动是固定夜晚子状态 `NIGHT_WITCH`，不再存在白天中断技能。
- `NIGHT_WITCH` 每晚都会作为公开主持/音频 pacing phase 进入；只有女巫存活且仍有至少一瓶药时才收集 `witch_action`，女巫无药或死亡时只追加 phase enter/exit，不调用 Agent。
- 女巫行动结束后继续进入 `NIGHT_SEER`，胜负只在 `NIGHT_RESOLVE` 后统一检查。
- 白天流程固定按 `DAY_SPEECH → DAY_VOTE → DAY_VOTE_PK? → DAY_EXILE? → DAY_LAST_WORDS? → CHECK_WIN` 推进；只有实际放逐者触发放逐遗言，平安日跳过。

---

## 3. 事件日志（Event Log）

### 3.1 设计原则

- **事件日志是单一事实源**：所有 PlayerView、回放、胜负判定都从事件日志派生。
- 事件**不可变**，append-only。
- 每个事件携带 `schema_version`，未来 schema 演化时保证向后兼容。
- 每局私有 metadata 包含 `random_seed`、`config_hash`、`seat_range`、`role_assignment`；这些字段由存储层的 `game_start` 记录，并用于 replay 校验。
- PlayerView 中的 `game_start` 必须经过 Referee 过滤：玩家本人只看到自己的角色，狼人额外看到狼队同伴；spectator 上帝视角可看到完整 `role_assignment` 用于观赛身份徽标。
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

- 流程：`game_start`, `phase_enter`, `phase_exit`, `game_end`, `role_reveal`
- 夜晚：`guard_protect`, `wolf_chat_message`, `wolf_kill_vote`, `wolf_kill_decided`, `wolf_tie_random`, `witch_action`, `seer_check`, `seer_check_result`, `no_death_tonight`, `death_at_night`
- 白天：`day_announce`, `last_words`, `speech`, `vote_cast`, `vote_result`, `vote_pk_enter`, `peaceful_day`, `exile`
- `vote_cast` 只在投票 phase 结算时公开追加；投票收集过程中不得提前写入 EventLog。弃票 `vote_cast` 使用 `{target: null, abstain: true}`。`vote_result` 仍然 public，`counts` 只统计非弃票目标，并通过 `abstain_count` / `abstentions` 暴露弃票数量与座位，继续作为前端直方图与叙事票型的来源。
- 系统：`win_check`, `agent_timeout`, `agent_invalid_action`, `agent_fallback_triggered`, `agent_budget_warning`
- 元数据：`llm_call`（包含 `prompt_hash`、`raw_response_hash`、`storage_ref`、model、token、cost，**仅写入存储层，不进 PlayerView**）
- `llm_call` payload 字段固定为：`prompt_hash: str`、`raw_response_hash: str`、`storage_ref: str`、`model: str`、`prompt_tokens: int`、`completion_tokens: int`、`cost_usd: float`、`prompt_version: str`。payload 不得包含 `raw_response` 原文。
- 随机：涉及平票随机、fallback 随机、角色洗牌的事件 payload 均记录 `rng_stream`、`candidates`、`selected`、`reason`。
- `role_reveal` 仅在 `GAME_END` 后由 Referee 生成，公开可见，payload 固定为 `{winner, seats: [{seat, role, alive}], highlights}`。`pacing_tick` 作为未来保留事件，STEP-07 不写入事件日志，避免污染 replay hash。
- `spectator_effect` **不是 EventLog 事件类型**，而是后端从 EventLog 派生的观赛投影：`{seq, day, phase, kind, actor, source_seat, target_seat, asset_key, duration_ms, meta}`。`kind` 固定为 `guard_shield | wolf_attack | seer_vision | witch_potion | death_reveal`。它只通过 spectator API/SSE 下发，不进入玩家视角、prompt、narrative 或 replay hash。`guard_shield`、`wolf_attack`、`seer_vision`、`witch_potion` 是现场观赛 transient effects，只能在非终局阶段播放；live pacing 中这些 effect 是动作完成后的可见节奏点，后端发布对应投影后可等待前端 `spectator_effect_rendered:<seq>` ack 或超时，再推进下一阶段。前端必须在座位叠层/药水动画挂载并短暂可见后再发送该 ack；若资源加载失败、浏览器禁用动画、页面重连或静音/自动播放限制导致无法完成真实播放，前端必须在本地超时内发送 fallback ack，后端也必须按 `WH_PACING_ACK_TIMEOUT_MS` 超时继续，ack 不得卡死现场流程。前端新建观赛对局必须显式使用 `live` pacing，并采用 `点击夜深了后立即进入游戏现场 -> start_paused=true 创建后端对局 -> 建立 SSE -> 最小现场壳挂载完成 -> POST /run` 的启动握手，确保首个夜晚现场 effect 不会在前端订阅前被写成历史；游戏音频、特效图片和其他静态资源只允许 best-effort lazy preload，不得阻塞进入游戏现场或 `/run`。SSE 中收到的 live transient effect 是现场座位叠层动画的唯一触发来源，REST 回补只能更新历史列表，不能推进 SSE cursor 或吞掉后续同 seq live effect。live SSE cursor 必须以“已发布投影”的 raw seq 为准；服务端不得让客户端 cursor 越过尚未发布 `spectator_effect` 的 private action seq。进行中的 live 观赛对局允许在 UI-only `localStorage` 快照中保存 `gameId`、席位分配、`seat_presentation`、启动状态、SSE raw cursor、effects cursor 与尚在可见窗口内的 recent transient effect queue，用于刷新、HMR 或页面重载后恢复订阅与继续渲染未 ack 的现场特效；该快照必须在退出、终局或复盘入口清理，不进入 EventLog、manifest、narrative、SSE、replay/resimulate 或 Referee/RuleEngine 边界。进入 `GAME_END` / `role_reveal` 后不得集中补播积压特效。复盘或 REST 回补中已发生的非死亡 transient effects 默认视为历史并标记为过期；`death_reveal` / `out_badge` 和 `role_reveal` 仍可在终局保留。

### 3.4 可见性规则

- 公共事件（`public: true`）：所有玩家可见（含死亡 Agent，见 §1.10）。
- 狼队事件：`wolf_kill_vote`、`wolf_kill_decided`、`wolf_tie_random` 仅狼队 seat 可见；`wolf_chat_message` 对狼队 seat 和 STEP-07 spectator 上帝视角可见。
- 狼人白天 prompt 额外执行上下文隔离：`DAY_SPEECH`、`DAY_VOTE`、`DAY_VOTE_PK`、`DAY_LAST_WORDS` 中，wolf seat 的 prompt payload `visible_events` 必须剔除 `wolf_chat_message`、`wolf_kill_vote`、`wolf_kill_decided`、`wolf_tie_random`，且不得注入 `wolf_private_context`。`NIGHT_WOLF_CHAT` / `NIGHT_WOLF_VOTE` 中，wolf seat 可通过独立 `wolf_private_context` 字段接收这些狼队私有事件，同类事件不得重复出现在 `visible_events`。
- 私有事件（`seer_check_result`, `guard_protect`, `witch_action`）：仅 actor 可见。
- `llm_call`、raw response 存储引用默认不进入任何 PlayerView；完整 `role_assignment` 只允许进入 spectator 上帝视角和存储/调试工具，不进入普通玩家 PlayerView。
- **Referee 是唯一权限边界**，PlayerView 由 Referee 按 visibility 过滤生成。

---

## 4. LLM 异常与 Fallback（写入 RuleSet）

### 4.1 三类异常

1. **超时**：单次调用 > `llm.timeout_seconds`，若 RuleSet 配置了 `fallback.phase_timeout_seconds[phase]` 则以该阶段值为准。
2. **非法 JSON / schema 校验失败**：Pydantic 解析失败。
3. **合法性校验失败**：通过 schema 但违反规则或文本事实一致性 hook（如刀狼队友、连守同一人、守卫声称确定守护成功）。

错误子类映射：

| 子类 | 外显事件 |
|---|---|
| `timeout` / `rate_limit` / `network` | `agent_timeout` |
| `invalid_json` / `schema_violation` / `illegal_action` | `agent_invalid_action` |

### 4.2 重试策略

- 每阶段每 Agent 最多重试 `fallback.max_retries` 次（默认 2 次，可配置）；若 RuleSet 配置了 `fallback.phase_max_retries[phase]` 则该阶段覆盖默认值。当前默认配置不再设置阶段级重试覆盖，确保正式对局 LLM 失败后按统一节奏重测。运行时必须优先使用 RuleSet 中的 retry 配置，环境变量只能作为 provider/default 配置来源，不能覆盖已加载 RuleSet 的阶段重试契约。
- 重试时在 prompt 末尾附加错误说明（仅本人可见），格式固定为：`上一次输出未被接受：{error_type}: {message}。请只返回符合 schema 的 JSON。`
- 失败后若仍有重试预算，按 RuleSet 中的固定退避序列 `retry_backoff_delays_seconds` 等待；当前默认序列为 `[1, 2]`，其中首次失败后的 `attempt=0` 使用 1 秒。超过序列长度的额外重试复用最后一个延迟。旧的指数退避字段仅作为旧配置兼容输入，不得覆盖显式固定序列。当前默认 `retry_backoff_jitter: false`，不得引入未记录或不可复现的随机 jitter。
- 通过 schema 但被 Referee 行动校验或文本事实一致性 hook 拒绝时，记录 `agent_invalid_action`，按同一阶段重试预算要求 Agent 重选/重写；重试仍失败 → 触发 fallback 并记录 `agent_fallback_triggered` 事件。

### 4.3 各阶段 Fallback 行为（默认）

| 阶段 | Fallback |
|---|---|
| `NIGHT_GUARD` | 随机选一个合法目标（排除昨晚守护对象） |
| `NIGHT_WOLF_CHAT` | 发送空消息（占位 `[沉默]`） |
| `NIGHT_WOLF_VOTE` | 随机选一个存活非狼或自己（fallback 不主动创建队友自刀跟票） |
| `NIGHT_WITCH` | 默认跳过，不消耗药品 |
| `NIGHT_SEER` | 随机选一个非自己玩家 |
| `DAY_SPEECH` | 基于 Referee 过滤后 PlayerView 的确定性公开发言模板 `contextual_public_speech` |
| `DAY_VOTE` | 随机选一个存活玩家（允许自己），fallback 不主动弃票 |
| `DAY_VOTE_PK` | 台下玩家随机投一个 PK 台上存活玩家；如无台下玩家可投，直接平安日 |
| `DAY_LAST_WORDS` | 默认模板「我没有遗言」 |

- 所有 fallback 行为均**写入 RuleSet**，黄金测试必须覆盖。
- 所有 fallback 随机均使用 deterministic RNG，并在对应事件 payload 中记录候选集、选中值与 fallback 原因。
- `contextual_public_speech` 只能读取当前 seat 的 PlayerView、公开/本人可见事件与 rule summary；不得读取 raw response、provider 配置、spectator-only 投影或任何未授权私有事件。
- 默认固定退避配置：`retry_backoff_delays_seconds: [1, 2]`、`retry_backoff_jitter: false`。
- 默认阶段超时覆盖：`DAY_SPEECH` 使用 18 秒超时；`NIGHT_WOLF_CHAT` 使用 10 秒超时；`NIGHT_WOLF_VOTE`、`DAY_VOTE` 与 `DAY_VOTE_PK` 使用 6 秒超时；`NIGHT_GUARD`、`NIGHT_WITCH` 与 `NIGHT_SEER` 使用 10 秒超时；所有阶段默认沿用 `fallback.max_retries: 2`。
- 默认观赛 pacing 倒计时与 LLM 单次超时分离：`DAY_SPEECH` 60 秒，`NIGHT_WOLF_CHAT` 90 秒，`NIGHT_WOLF_VOTE` / `DAY_VOTE` / `DAY_VOTE_PK` 30 秒，`NIGHT_GUARD` / `NIGHT_WITCH` / `NIGHT_SEER` 20 秒；ack 仍只控制现场观赛节奏，不写入 EventLog，不影响 replay hash。

### 4.4 上下文管理策略

- Prompt 上下文只从 Referee 过滤后的 `PlayerView.visible_events` 构造，不读取未授权事件。
- 默认事件窗口为最近 40 条，并强制保留 `game_start`、`day_announce`、`death_at_night`、`exile`、`vote_result`、`vote_pk_enter`、`witch_action`、`seer_check_result` 等关键事件。
- `DAY_SPEECH`、`DAY_VOTE`、`DAY_VOTE_PK`、`NIGHT_WOLF_CHAT` 与 `NIGHT_WOLF_VOTE` prompt 中公开发言集中进入 `speech_context`，默认只保留最近 12 条公开发言；`visible_events` 不重复携带大量 `speech` 事件，避免长局发言 prompt 膨胀。
- 当可见事件超过 60 条时，payload 使用确定性长局摘要：首 10 条事件 + 中间摘要 + 最近 30 条事件。
- 摘要格式固定为 `{type, day, phase, actor, summary_text}`，其中 `type` 为 `summary`，摘要由事件日志纯函数生成，不调用 LLM。
- 上下文选择和摘要不得改变 EventLog、replay hash、PlayerView 权限边界或行动合法性。

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
narrative.jsonl
final_reveal.json
review_report.json
```

`events.jsonl` 与 EventLog 一一对应；`narrative.jsonl` 每行记录 spectator-safe 中文叙事；`final_reveal.json` 记录终局身份揭晓；`review_report.json` 记录赛后 AI 复盘报告。`review_report.json` 是从 Referee 过滤后的 spectator events、`narrative.jsonl`、`final_reveal.json` 和 manifest 中的 `seat_presentation` 派生的赛后产物，不进入 EventLog、PlayerView、narrative、SSE、玩家行动 prompt 或 replay/resimulate 校验，不影响 replay hash。STEP-08 起复盘报告 schema 固定为 `1.1`，包含 `generation_mode: real_ai | offline_mock`、summary、leaderboard、players、key_decisions、counterfactuals；leaderboard 的 `reason` 字段用于一段式概括该模型/玩家本局整体表现，必须覆盖角色、关键公开证据、排名原因和短板，不再只放单条证据或短排序理由；players 使用六边形评分 `scores: [{key, label, value}]`，六轴固定为发言质量、推理逻辑、票型执行、阵营贡献、信息控制、角色职责，其中角色职责按身份显示为狼队协同、查验价值、药水决策、守护判断或平民职责。赛后评审 provider 使用独立模板 `configs/prompts/zh/review/report.v1.md`，只服务 `POST /games/{id}/review-report`；该模板必须要求先抽取公开证据再生成报告，每名玩家引用独有公开证据，优先覆盖发言、票型、死亡/存活节点和角色职责，禁止无事实支撑地复用泛化优缺点或建议；`key_decisions` 必须围绕影响胜负或阵营结构的公开节点写清发生了什么、为什么关键、对胜负的影响，`counterfactuals` 必须基于关键决策推演公开选择改变后的可能局势与下一局启发，不得引入未公开私有行动。修改 review prompt 不改变报告 schema、已有 v1.1 缓存策略、EventLog、PlayerView、narrative、SSE、fallback、ack、replay hash 或 resimulate。旧版 `1.0` 报告视为过期缓存，`GET` 按未生成处理，`POST` 可重新生成并覆盖。`manifest.json` 可记录 spectator-safe 的 `seat_presentation` 展示快照，仅允许包含 `{seat, nickname, icon_path}` 这类本地 UI 展示信息，不得包含 provider、model name、base URL、API key、raw response、prompt 或任何私有行动结果；该字段不进入 EventLog，不参与 replay hash 或 resimulate。`raw_responses.jsonl` 每行记录 `{storage_ref, seat, phase, day, seq, model, prompt_hash, raw_response_hash, raw_response, prompt_tokens, completion_tokens, cost_usd, prompt_version}`。`raw_responses.jsonl` 不保存 prompt 原文，只保存 `prompt_hash` 与 `prompt_version`；prompt 内容正确性通过测试捕获 provider 入参验证。所有文件权限为 `0600`。JSON/JSONL 写入必须采用 tmp + fsync + atomic rename 或行级 fsync；恢复时若末行损坏，截断到最后一条可解析完整 JSONL。

### 5.3 Prompt 模板版本号

- `configs/prompts/zh/seer/night_action.v5.md`，文件名带版本号。
- 事件日志记录 `prompt_version`，修改 prompt 后老日志仍可解释。

---

## 6. Prompt 注入与越权防御

### 6.1 输入侧（PlayerView）

- Referee 不做开放式语义审查，只保证注入到 prompt 的私有信息正确脱敏，并对输出文本执行确定性事实一致性 hook。
- Agent 在发言里声称「我查了 3 号是狼」属于**合法角色扮演**，由游戏机制处理（信任/怀疑）；但不得输出可由规则和本人可见历史确定为不可能或越权的事实。
- 文本事实一致性 hook 至少覆盖：守卫不得声称连续两晚守同一人；守卫不得把“守护成功/挡刀成功”说成确定事实；任意玩家不得引用未授权狼聊、狼刀目标、provider、model name、raw response 或事件 schema 名作为可见事实。
- 文本事实一致性 hook 还必须覆盖顺序发言事实：`DAY_SPEECH` 中尚未完成当前白天公开发言的存活座位，不得被说成不报查验、未回应、沉默、划水、不活跃、发言少或藏身份；该类输出按 `illegal_action` 重试与 fallback 处理。
- 泄漏测试覆盖：预言家结果、狼队身份、狼刀细节、守卫目标和 `last_guard_target` 不出现在非授权玩家的 PlayerView / prompt payload 中。

### 6.2 输出侧

- 所有 LLM 输出必须走 Pydantic / JSON Schema 校验。
- Schema 校验通过后必须进入 Referee 行动合法性校验；`DAY_SPEECH` / `DAY_LAST_WORDS` 还必须进入文本事实一致性 hook。任何失败都按 §4 重试与 fallback 处理。

输出 JSON schema 按 phase 固定为：

| phase | 字段 |
|---|---|
| `NIGHT_GUARD` | `{target: int}` |
| `NIGHT_WOLF_CHAT` | `{text: str}` |
| `NIGHT_WOLF_VOTE` | `{target: int}` |
| `NIGHT_WITCH` | `{action: "save" | "poison" | "skip", target: int | null}` |
| `NIGHT_SEER` | `{target: int}` |
| `DAY_SPEECH` | `{text: str}` |
| `DAY_VOTE` | `{target: int | null}` |
| `DAY_VOTE_PK` | `{target: int | null}` |
| `DAY_LAST_WORDS` | `{text: str}` |

提示词结构固定为：

```text
[system.{version}.md] + [role/phase.{version}.md] + [JSON payload] + [retry_error?]
```

`system.v5.md` 是当前默认全员统一系统提示词，旧 `v1` / `v2` / `v3` / `v4` 文件保留用于回放兼容；角色/phase 文件来自 `configs/prompts/{language}/{role}/{kind}.{version}.md`。赛后复盘评审不使用玩家行动 prompt 结构，固定加载 `configs/prompts/zh/review/report.v1.md` 并追加 spectator-safe JSON payload；该 payload 只包含 spectator events、narrative rows、role reveal、seat_presentation、score_axes 和 output_schema，不得包含 raw response、provider、API key、玩家行动 prompt 原文或未授权私有行动结果。`v5` 继承 `v4` 的 `text` 输出质量约束和角色策略，并仅增强狼人夜间刀口判断：首夜平安夜应优先按女巫救人高概率评估，不得仅因无人死亡就认定首夜刀口被守卫守护；第二夜若可信预言家已暴露，即使首夜刀口在外置位，也要把守卫今晚可能守预言家作为主要风险；守卫不可连续守同一目标只能用于真实高置信的上一夜守护目标，不能机械套用到可能被女巫救下的首夜刀口。狼人仍不得机械刀守卫大概率守护的明预，可换刀女巫、守卫、强民或外置神，并可少量自刀骗药或做身份；女巫首夜默认救但不无脑，银水不等于铁好，刀口明显像自刀或留解药能逼狼刀时可跳过；守卫按轮次守人，明预可信也不能机械连续守同一人；预言家、村民和投票围绕查验链、发言矛盾、票型和强推可信好人的行为站边。`v5` 不改变输出 JSON schema、事件 schema、PlayerView payload 字段、fallback、ack、EventLog、replay hash 或 resimulate 语义。`DAY_SPEECH` / `NIGHT_WOLF_CHAT` 的模型正常输出若为空、纯占位或直接为 `[沉默]`，按 schema violation 进入重试与 fallback，只有 fallback 路径可生成 `[沉默]`。`JSON payload` 只包含 seat、role、phase、rule_set_summary、teammates、Referee 过滤后的 visible_events、由 visible_events 纯函数派生的 speech_context、output_schema，以及仅 wolf 夜聊/狼刀阶段允许出现的 `wolf_private_context`。`rule_set_summary` 必须包含公开投票规则 `vote_sheriff` 与 `can_abstain`，当前 `vote_sheriff` 固定为 `false`，供提示词明确禁用警长、警徽、警上警下和警长归票机制；`can_abstain` 控制 `DAY_VOTE` / `DAY_VOTE_PK` 是否允许输出 `target: null` 弃票。`speech_context` 用于 DAY_SPEECH 的发言归属约束，也用于投票和狼人夜间阶段压缩公开发言上下文；固定包含 `current_seat`、`already_spoken_seats`、`not_yet_spoken_seats`、`own_public_speeches`、`prior_public_speeches`，其中 `not_yet_spoken_seats` 仅表示当前白天仍未轮到或尚未完成公开发言的存活座位，不得被解释为沉默、划水、不活跃或藏身份。`speech_context` 不得引入未经过 Referee 过滤的事件、昵称、provider、raw response 或私有信息。`prompt_version` 写入 manifest 与 LLM 调用索引；replay / resimulate 必须优先使用 manifest 中记录的版本解释日志，缺失时回退 `v1`。

`v5` 顺序发言补充：所有角色的 `DAY_SPEECH` prompt 必须说明只能评价已经出现在 `speech_context.prior_public_speeches` 的公开发言；`not_yet_spoken_seats` 只表示尚未轮到，不能作为不报查验、未回应、沉默、划水、不活跃、发言少或藏身份的证据。`DAY_VOTE` / `DAY_VOTE_PK` prompt 只能把已经完成的公开发言、公开票型、夜晚公示和可见查验链作为投票依据，不得把后置位未发言作为投票理由。判断预言家是否报查验，只能基于该座位已经公开发言后的文本。

`v5` 守卫白天策略沿用 `v4` 补充：守卫低收益时不主动跳身份；但在公开发言、公开票型或 PK 局势显示自己高概率被误放逐时，应明牌守卫自救，并给出可公开、可验证的关键守护线索。该补充只改变 prompt 策略文本，不改变输出 JSON schema、事件 schema、PlayerView payload 字段、fallback、ack、replay 或 resimulate 语义。

### 6.3 PlayerView 大小控制

- 使用 §4.4 的**重要事件优先 + 最近事件窗口 + 确定性历史摘要**，避免 prompt 无限增长。
- 摘要算法是基于可见事件的纯函数，保证可复现。
- 每局 token 上限通过 `llm.budget_per_game` 配置，超限触发告警（不强制中止）。

---

## 7. 目录结构

```
.
├── architecture.md                          # 主架构文档（本文档落地后扩写）
├── plan.md                                  # 本计划
├── configs/
│   ├── games/
│   │   ├── classic_10.yaml                  # 默认 10 人局完整配置
│   │   ├── classic_8.yaml                   # 旧版 8 人局兼容配置
│   │   ├── _role_packs/
│   │   │   ├── classic_10_witch_guard_seer.yaml
│   │   │   └── classic_8_witch_guard_seer.yaml
│   │   └── _rule_sets/
│   │       └── majority_or_side_elimination.yaml
│   ├── models/
│   │   ├── providers.yaml
│   │   └── roster.yaml
│   └── prompts/
│       ├── zh/system.{v1,v2,v3,v4,v5}.md
│       ├── zh/{seer,guard,wolf,witch,villager}/{night_action,speech,vote,last_words}.{v1,v2,v3,v4,v5}.md
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
│       │   ├── model_icon_minimax_laoshi.png   # 系统设置 10 个模型图标（见 §14.11）
│       │   ├── model_icon_wanwen.png
│       │   ├── model_icon_guangzhimingmian.png
│       │   ├── model_icon_dami.png
│       │   ├── model_icon_xueba.png
│       │   ├── model_icon_xiaodoubao.png
│       │   ├── model_icon_haiseyin.png
│       │   ├── model_icon_gemini.png
│       │   ├── model_icon_claude.png
│       │   └── model_icon_gpt.png
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
│   │   └── modelConfigs.ts                  # 10 个模型 slot 静态配置（见 §14.11）
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
- `roster.yaml` 将 10 个座位绑定到模型 profile，支持 personality tag。
- 成本记录**落盘**（per-game token usage + cost），方便后期对账。
- 超过单局预算时发出一次 `agent_budget_warning` 系统事件；游戏继续运行，不因预算告警中止。

#### 环境变量

STEP-06 引入以下环境变量（通过 `pydantic-settings.BaseSettings` 读入，封装在 `src/wolven_hunt/config/settings.py`）：

- `WH_LLM_PROVIDER`：`mock` | `litellm`，缺省为 `mock`；非法值启动失败
- `WH_LLM_API_KEY`：真实 provider 的 API key；`WH_LLM_PROVIDER=litellm` 时必填
- `WH_LLM_BASE_URL`：LiteLLM base URL，可选
- `WH_LLM_MODEL`：默认模型名，可选（roster.yaml 可覆盖）
- `WH_LLM_TIMEOUT_SECONDS`：单次调用超时，默认 30
- `WH_LLM_MAX_RETRIES`：重试预算，默认 4；已加载 RuleSet 的 `fallback.max_retries` 优先
- `WH_LLM_BUDGET_PER_GAME`：单局 token 上限，默认 100000
- `WH_LLM_PROVIDER_MAP`：空字符串或 YAML 路径；非空时按座位路由 provider，缺失座位回退到全局 `WH_LLM_*`
- `WH_REVIEW_PROVIDER`：赛后 AI 复盘报告 provider，`mock | litellm`，默认 `mock`；`litellm` 生成 `generation_mode=real_ai`，`mock` 生成明确标记的 `generation_mode=offline_mock`
- `WH_REVIEW_API_KEY`：赛后报告真实 provider 的 API key；仅 `WH_REVIEW_PROVIDER=litellm` 且触发报告生成时需要，缺失时生成失败但不得静默降级为 mock
- `WH_REVIEW_BASE_URL`：赛后报告 LiteLLM base URL，默认 `https://yunwu.ai/v1`
- `WH_REVIEW_MODEL`：赛后报告模型名，默认 `gpt-5.5`
- `WH_REVIEW_TIMEOUT_SECONDS`：赛后报告单次调用超时，默认 60
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

### 9.2 FastAPI 接口（STEP-06 实现）

- `POST /games`：创建一局；可选 `seat_presentation: Record<seat, {nickname, icon_path}>` 仅作为 spectator-safe UI 展示快照写入 manifest，不写 EventLog
- `GET /games/{id}`：当前状态（Referee 过滤后的 spectator 视角），返回 `seat_presentation`；旧 run 没有该字段时返回空对象
- `GET /games/{id}/events`：事件日志（spectator 上帝视角；包含身份表和狼聊，不含 raw response / provider 配置 / 守卫和预言家私有事件 / 狼刀细节）
- `GET /games`：STEP-08 历史对局列表，从 `runs/{game_id}/manifest.json` 汇总，不能包含 API key 或 raw response
- `POST /games/{id}/run` / `pause` / `resume`：流程控制
- `POST /games`：创建对局；`start_paused=true` 时只注册 session 与 manifest，不启动 FSM，供现场观赛前端先建立 SSE 后再 `/run`
- `POST /games/{id}/run`：启动或恢复已创建对局；对 `start_paused=true` 的 session 负责启动 FSM
- `POST /games/{id}/replay`：触发 replay（参数：`mode=deterministic|resimulate`）
- `POST /games/{id}/dev/inject`：dev-only，注入动作
- `GET /games/{id}/stream`：SSE 流式推送事件
- `GET /games/{id}/narrative`：返回 spectator-safe 中文叙事行，支持 `?after=<seq>`
- `GET /games/{id}/effects`：返回从完整 EventLog 派生的 spectator-only 特效行，支持 `?after=<seq>`；不得包含 raw response、provider 配置、prompt、模型名或玩家不可见事件原文。
- `GET /games/{id}/reveal`：仅游戏结束后返回 `final_reveal.json`；未结束返回 `404 {code: "game_not_finished"}`
- `GET /games/{id}/review-report`：返回已生成的赛后 AI 复盘报告；未生成返回 `404 {code: "report_not_generated"}`
- `POST /games/{id}/review-report`：仅游戏结束后生成或返回有效缓存的赛后 AI 复盘报告。报告 prompt 只能使用 spectator-safe events、narrative、role reveal 与 `seat_presentation`，不得读取 `raw_responses.jsonl`、provider 配置、API key、prompt 原文或未授权私有事件；真实 provider 配置存在时必须调用真实 review provider，未配置时允许生成 `offline_mock` 离线复盘，真实 provider 失败不得静默降级；生成失败不改变 EventLog、replay hash 或历史列表。
- `POST /games/{id}/ack`：前端音频或现场 transient effect 渲染完成后解除 pacing 等待；effect ack event 名称为 `spectator_effect_rendered:<seq>`；ack 不进事件日志、不影响 replay hash
- `POST /games/{id}/speech`：提交公开发言文本，仍走 Referee `validate_action`
- `POST /games/{id}/wolf_chat`：提交狼聊文本，仍走 Referee `validate_action`
- `POST /models/test`：STEP-08 后端代理模型连通性测试，不写 EventLog、不落盘、不回显 API key
- 错误体统一为 `{code: str, message: str, details?: object}`；4xx 表示业务/规则拒绝，5xx 表示系统错误。

SSE 线协议固定为：

```
event: game_event
id: <seq>
data: <spectator Event JSON>
```

STEP-07 额外推送同源 `event: narrative_row` 与 `event: spectator_effect`，三类事件共享原始 EventLog `seq`。live SSE cursor 按已完成 spectator/narrative/effect 投影发布的 raw seq 推进；每条 raw event 独立决定是否产生 filtered `game_event`、`narrative_row`、`spectator_effect`，但服务端只有在该 raw event 的所有投影都写入 session 后才允许 SSE 消费该 seq。服务端可在 SSE 建立时先发送 `event: stream_ready` 控制帧用于解除前端启动握手等待；该帧不带 `id`，不对应 EventLog 事件，不推进 cursor，不进入 narrative、spectator projection、manifest、replay/resimulate 或 replay hash。每 30s 发送 `event: heartbeat\ndata: {}`。客户端携带 `Last-Event-ID: <seq>` 时，服务端从 `seq + 1` 续推；请求的 seq 不存在时返回 410。STEP-08 开始前端默认走同源相对路径；dev 由 Vite 7001 proxy 到后端 7002，prod 由 FastAPI 7002 同源服务静态文件和 API。

---

## 10. 测试计划

### 10.1 规则黄金测试（unit + golden）

- 预言家：查活人、查死人、重复查验、死亡后不调用、结果只返回阵营、不能查自己。
- 胜负：狼严格人数优势胜、村民边全灭狼胜、神职边全灭狼胜、狼全灭好人胜、每个检查点都触发。
- 流程：首夜狼刀/双奶死亡并触发遗言、首夜毒药死亡无遗言、第二夜及以后夜死无遗言、首夜守卫平安夜、女巫救人、女巫毒人、双奶死亡、同夜双死、平票 PK、二次平票平安日、遗言规则、首日规则。
- 死亡 Agent 停用 + 仍接收公开事件。

### 10.2 泄漏测试（leakage）

- 预言家结果仅本人 PlayerView 可见。
- 狼队身份/夜聊/投刀仅狼队可见。
- 守卫目标仅守卫本人可见。
- 女巫用药、狼刀目标和药品剩余状态仅女巫本人授权视角可见。
- 所有死亡事件不暴露死因。

### 10.3 异常路径测试

- LLM 超时、非法 JSON、违规动作 → 重试 → fallback。
- 每阶段 fallback 行为符合 §4.3 表格。
- fallback 随机行为在固定 seed 下完全可复现。

### 10.4 流程测试（integration）

- mock 10 个 deterministic Agent 跑 100 局，断言：
  - 无异常退出；
  - 胜负必收敛（不存在死循环）；
  - 事件日志可被 `replay_deterministic` 完整重放；
  - 事件日志可被 `replay_resimulate` 重跑且结果一致。
- 女巫在 `NIGHT_WITCH` 行动；行动后继续预言家查验并统一进入夜晚结算。
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
| P0 | 目录骨架 + 配置模板（classic_10.yaml + rule_set + role_pack，保留 classic_8 兼容配置） | 第一阶段交付物 |
| P0 | `.env.example` + `.gitignore` | 安全前置 |
| P0 | 前端入口壳（大厅 Home）+ 资源构建脚本 | 单独交付物，不阻塞 Python 引擎进度；契约见 §14 |
| P1 | RuleEngine 纯函数 + 事件 schema 实现 | 核心 |
| P1 | Referee + PlayerView + 泄漏测试 | 权限边界 |
| P1 | FSM 编排 + mock Agent + 100 局集成测试 | 跑通闭环 |
| P2 | LLM 网关（LiteLLM + 重试 + fallback + 成本记录） | 接入真模型 |
| P2 | Replay 两种模式 + Prompt 版本号 | 长期可维护 |
| P2 | FastAPI + SSE | 外部接入；第一阶段只在 architecture.md 定义接口边界 |
| P3 | STEP-07 观赛 MVP：per-seat provider、pacing/ack、narrative、role reveal、前端音视频与终局定格态 | 可从前端完整观看一局 AI 狼人杀 |
| P3+ | Property test、公平性回归、Token 预算测试 | 工程化体验 |

---

## 12. 假设与待确认项

1. **预言家可查死人**为首版明确规则，不视为调试特权。
2. **不能查验自己**作为默认规则，后续可通过 RuleSet 开关扩展。
3. **狼人人数 > 好人人数**按严格大于 `>` 实现。
4. **首夜可以死亡**作为默认，`first_night_can_die: true`。
5. **首夜狼刀死亡和双奶死亡者有遗言**；毒药导致死亡任何情况下无遗言；第二夜及以后夜死无遗言。
6. **女巫每晚最多使用一瓶药**，解药和毒药每局各一瓶；解药只能救当晚狼刀目标，毒药不能毒自己。
7. **投票允许投自己**，但不能投死亡玩家。
8. **PK 重投只投 PK 台上玩家**，PK 台上玩家不参与重投；二次平票平安日入夜。
9. **死亡 Agent 仍接收公开事件**，便于回放完整性。
10. **Referee 不审查发言内容**：发言里的虚假信息属合法策略。
11. **STEP-07 / P3 阶段开始实现观赛 MVP**：per-seat provider map、pacing/ack、narrative/reveal API、前端音视频、倒计时和终局定格态可以落地；CI 默认仍使用 mock provider。
12. **STEP-08 / P3 生产可玩阶段**：目标是 10 个 AI 自动对局可从前端无卡点观赛到终局。允许实现同源部署、单命令启动、后端模型连通性测试代理、SSE 自动重连、pacing 模式切换、历史复盘 UI、生产静态文件服务和 CI。默认测试仍使用 mock provider；真实 LLM smoke 必须由环境变量显式开启。

## 13. 项目系统提示词与变更纪律

- 仓库根目录 `AGENTS.md` 是本项目的开发代理系统提示词。
- 此后任何代码变更、配置变更、prompt 变更、测试变更或架构契约变更，都必须先检查本 `plan.md`。
- 如果实际实现需要改变本计划中的规则、目录、接口、FSM 子状态、事件 schema、fallback、replay 或测试约定，必须先更新 `plan.md`，再修改代码或配置。
- 如果变更只是落实现有计划，也要确保新增文件、模块命名和行为边界与本 `plan.md` 保持一致。
- `architecture.md` 是本计划的架构契约落地文档。后续实现不得绕过其中定义的 Referee 权限边界、事件日志单一事实源、配置驱动规则、纯 Python FSM 优先、可复现 replay 和 LLM fallback 约束。

以上假设若有不同意见，请在进入实施前明确。

### 13.1 STEP-08 Playable AI Game Contract

- 本阶段范围固定为「10 个 AI 自动对局 + spectator 观赛」，不实现真人入座、多人房间或玩家私有视角。
- 默认开发端口为前端 Vite `7001`、后端 FastAPI `7002`。前端运行时 API base 默认空字符串，即同源相对路径；开发模式通过 Vite proxy 转发 `/games`、`/models`、`/healthz`。
- 生产模式由 `wolven-hunt serve-prod` 设置 `WH_SERVE_STATIC=true`，FastAPI 在 API 路由之后挂载 `dist/`，单端口 `7002` 同时服务前端和 API。
- 前端模型连通性测试必须走后端 `POST /models/test`。浏览器不得再直接向第三方模型 base URL 发请求；连通性测试失败后前端按固定序列 `1s → 3s → 5s → 10s` 自动重测，任一尝试成功即视为通过；全部失败后展示最后一次脱敏错误。连通性测试失败不能永久阻止开局，用户可选择继续开局，运行期失败由 LLM 重试与 fallback 兜底。测试请求使用 30 秒超时；正式游戏 `AgentSpecLLM` 继续使用阶段 RuleSet timeout。测试请求与正式游戏 `AgentSpecLLM` 均允许携带 `thinking_enabled`，未携带时默认为 `false`；Qwen 系列必须把 `thinking_enabled` 显式映射为 provider 请求中的 `enable_thinking: true/false`，其他模型仅在 `true` 时追加 provider 兼容的 thinking 参数。OpenAI-compatible provider 若明确拒绝非流式请求并要求 `stream`，后端可用同一请求参数自动重试 `stream: true` 并聚合 delta 文本；该兼容重试不进入 EventLog、PlayerView、narrative、spectator API、manifest 或 SSE，不影响 replay hash。正式游戏中的 `thinking_enabled` 只影响 provider 调用参数，不进入 EventLog、PlayerView、narrative、spectator API、manifest 或 SSE，不影响 replay hash。
- `POST /models/test` 只做临时 provider 调用，不写入 `runs/`、EventLog、raw response、cost 或 narrative，不返回或记录 API key；失败响应只返回脱敏后的短错误摘要，供前端展示诊断信息。
- 所有模型 provider 调用必须直连，不继承系统 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` / `NO_PROXY`；LiteLLM 导入阶段和请求阶段都必须禁用环境代理，不通过安装 SOCKS 依赖来兜底。
- 历史复盘只消费 Referee 过滤后的 spectator 上帝视角。`GET /games` 从 `runs/` 汇总 manifest；`GET /games/{id}/events` 在线时返回 session spectator events，离线历史从 `events.jsonl` 读取并按 spectator 过滤，不读取 `raw_responses.jsonl`。
- `seat_presentation` 是历史复盘恢复游玩时头像和昵称的展示快照，必须只包含本地 `/assets/lobby/` 头像路径和有限长度昵称；它不改变身份来源、胜负判定、行动合法性、ack、EventLog、replay hash 或 LLM 输入。
- 游戏结束后的前端结算使用“终局定格态 + 可展开复盘抽屉”：默认保留原游戏舞台、座位、聊天框、投票直方图、身份徽标和出局标记，只叠加极简胜负与操作控件；详细复盘默认收起，只展示 `role_reveal.highlights` 和 spectator-safe 身份全览，不直接暴露 raw event JSON。终局定格态不得继续播放或补播 `guard_shield`、`wolf_attack`、`seer_vision`、`witch_potion` transient spectator effects。
- STEP-08 起终局定格态的复盘入口文案为「生成复盘报告」：点击后按钮禁用变灰并显示 spinner 与「正在生成中」，生成成功后变为「查阅报告」。报告抽屉展示战局摘要、生成模式标识、Leaderboard/排行榜、每名玩家角色感知六边形评分、具体评语与公开证据、关键决策复盘、反事实推演与对应建议；不得展示 game id、schema、generated_at、provider、model name、API key、raw response 或 prompt。大厅「历史复盘」入口和列表内「复盘」按钮不改名、不接入报告生成。
- 点击「夜深了...」后，前端必须立即切入游戏现场并展示座位/阶段壳；随后通过同源 `GET /healthz` 做轻量本地服务健康检查。失败时仅显示 UI-only 的「正在连接本地服务」/连接失败提示，不创建对局、不写入 `localStorage` 快照、不进入 EventLog、narrative、SSE、manifest 或 replay/resimulate 校验。健康检查通过后，仍按 `start_paused=true -> 建立 SSE -> 最小现场壳 mounted -> POST /run` 握手；SSE 已连接且等待 `/run` 推进期间显示 UI-only 的启动/等待提示。服务端可在 SSE 建立时先发送 `event: stream_ready` 控制帧用于解除前端启动握手等待；该帧不带 `id`，不对应 EventLog 事件，不推进 SSE cursor，不进入 narrative、spectator projection、manifest、replay/resimulate 或 replay hash。启动提示可展示已等待秒数和加载动效，但不得写入 EventLog、narrative、manifest 或 replay/resimulate 校验，也不得改变 ack、pacing、SSE cursor 或后端启动接口语义；收到 `GAME_START` 或 `/run` 已接受后应退出“正在启动对局”的阻塞态，后续改用当前 phase/等待模型/等待音频或特效确认等现场状态。
- `manifest.json` 从 STEP-08 起必须包含 `config_path` 与 `prompt_pack_version`，用于 `replay_resimulate(config_path=None)` 恢复原配置与 prompt 版本。缺失时只能回退 classic_8 与 prompt `v1`，并需保持旧 run 兼容；新 run 默认使用 classic_10 与 prompt `v5`。
- 前端 SSE 必须支持断线重连、`Last-Event-ID` 续传、最多 4 次固定延迟重试，延迟序列为 `1s → 3s → 5s → 10s`，不使用 jitter；超过上限显示可操作错误，不静默停住。断线时通过 REST 拉取 narrative/effects 只能作为历史补齐，不得更新用于 `Last-Event-ID` 的 raw event cursor，也不得清空或过期已经由 SSE 收到且仍在播放的 live transient effect；cursor 只能由 SSE raw event id 推进，且 narrative-only 回调不得把 cursor 推过同 seq 尚未消费的 `spectator_effect`，避免私有动作派生的 live effect 被回补吞掉。
- 进行中的 live 观赛对局允许写入 UI-only `localStorage` 快照，用于刷新、HMR 或页面重载后恢复 `gameId`、席位分配、`seat_presentation`、启动状态、SSE raw cursor、effects cursor 与尚在可见窗口内的 recent transient effect queue，并重新订阅 SSE；该快照必须在退出、终局或复盘入口清理，不进入 EventLog、manifest、narrative、SSE、replay/resimulate 或 Referee/RuleEngine 边界。
- ack 仍只控制现场 pacing，不写 EventLog，不影响 replay hash。localStorage key `wolven_hunt.pacing_mode` 仅影响新建对局传入的 pacing profile。游戏内阶段语音使用独立于大厅 BGM 的本地状态与右上角开关，不能复用 `wolven_hunt.lobby.muted` 导致观赛语音被静音；阶段音频播放失败、effect 渲染 ack 丢失或浏览器阻止自动播放时，前端必须在超时内发送 ack，后端也必须按 `WH_PACING_ACK_TIMEOUT_MS` 超时继续推进。
- 默认硬编码模型 key 保留为产品策略：作者自费轮换，用户可在设置里覆盖。README、StartModal 与 ModelConfigList 必须明确该策略。

## 14. 前端入口骨架（Web Lobby Shell）

第一阶段除了 Python 引擎骨架外，前端只交付一个**大厅 Home 壳**，用于承接素材并作为后续接入 FastAPI 的可见入口。本节冻结前端壳的契约，使其与 §1–§6 的规则契约**互不影响、互不导入**。

### 14.1 模块边界

- 前端代码统一放在仓库根目录：`package.json`、`package-lock.json`、`index.html`、`vite.config.ts`、`tsconfig.json`、`tsconfig.node.json`、`src/components/`、`src/hooks/`、`src/main.tsx`、`src/App.tsx`、`src/styles.css`、`public/`。
- 与 `src/wolven_hunt/` Python 引擎在同一仓库下共存，但**双向不导入**：前端不通过任何方式引用 `src/wolven_hunt/*` 或 `configs/*`；Python 引擎也不依赖前端。
- 前端只消费 **Referee 过滤后的 spectator 视角**。STEP-07 观众页可展示全部身份与狼人夜聊；任何玩家视角、行动校验、raw response、provider 配置、守卫/预言家私有事件和狼刀细节均通过 FastAPI/Referee 边界控制，前端**不得绕过 Referee**。
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
  - `model_icon_gemini.png`（源自 `素材/Gemini.png`）
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

- 系统设置弹窗内含 10 个模型 slot，每个 slot 由两部分组成：
  - **静态部分**（不进 `localStorage`）：`slot` 索引、中文 `nickname`、ASCII `iconPath`，统一定义在 `src/lib/modelConfigs.ts` 的 `MODEL_SLOTS` 常量数组。
  - **默认模型输入部分**：`baseUrl` / `apiKey` / `modelName` / `thinkingEnabled`，统一定义在 `src/lib/modelConfigs.ts` 的 `MODEL_CONFIG_DEFAULTS`，用于预填系统设置；10 个默认 slot 的 `thinkingEnabled` 固定为 `false`。
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
- 过渡触发时同步暂停大厅 BGM，但不写入 `wolven_hunt.lobby.muted`；游戏页使用独立的游戏语音开关与 `wolven_hunt.game.*` 本地状态。退出后不自动还原大厅 BGM，用户可手动开启。
- 游戏页布局：白天背景图全屏 cover，10 个席位分左右两列（左 5 / 右 5）垂直居中分布；席位圆圈使用响应式尺寸，保证桌面和移动端不重叠。
- 席位状态：空态显示圆形虚线边框 + lucide `Plus` 图标；已分配态显示模型头像 + 加粗昵称（昵称在圆圈外侧，左列右侧 / 右列左侧，白天背景下需增强文字阴影）。
- 席位编号：每个席位圆圈始终显示 1-based 编号徽标；左列自上而下 1–4 且徽标在左下角，右列自上而下 5–8 且徽标在右下角。编号仅是游戏准备页 UI 辅助，不进入 Referee / FSM / RuleEngine 边界。
- 席位身份位（`.game-seat-role`）本步骤为占位 `<span>`（`display: none`），留给后续步骤填充。
- 模型选择：点击席位（无论空态或已分配）→ 打开游戏页自有 `ModelPicker` 弹窗（不复用大厅 `LobbyModal` 或 `settings_panel_bg.png`）→ 列出 10 个模型卡片 → 已被其他席位占用的卡片主体置灰 + `disabled`，但在右下角显示图标型「交换」按钮；点击该图标只把当前席位模型与该模型所在席位互换，不产生重复 slot。当前席位已选项黄色边框高亮。
- 模型分配规则：每个 model slot 在 10 席位中至多出现一次；点击已分配头像可重新选择，旧 slot 释放回可选池。交换席位只调换 `assignments` 中两个位置，不写 `localStorage`、事件日志或 replay，也不清空按 model slot 记录的连通性测试结果。左下角显示小浣熊装饰入口（`quick_assign_raccoon.png`）与「一键分配」按钮，点击后仅在前端 UI 内用 Fisher-Yates 洗牌把 10 个 `MODEL_SLOTS` 随机分散到 10 个席位；该随机只影响当前页面内存中的 `assignments`，不写事件日志、不参与 replay、不进入 Referee / FSM / RuleEngine。触发后清空旧 `testResults` 与测试状态提示，用户需重新测试模型连通性。
- 游戏准备页未开局时**不持久化**席位分配到 `localStorage`，刷新页面后回到初始态；点击「夜深了...」创建 live 观赛对局后，可按 §13.1 写入进行中对局恢复快照，且退出或终局后必须清理。
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
  - "测试模型连通性" 按钮：10 席全部分配前 disabled；填满后启用，点击触发并行 LLM 测试。
  - "夜深了…" 按钮：10 席全部分配且全部测试 ✓ 前 disabled；点击触发 `transitionToStage({ dayNumber, phase: 'night' })`。
- **席位测试态**：`<GameSeat />` 新增 `testStatus?: ModelTestStatus` prop。`testing` 显示头像灰度 + 三点 pulse 动画（JSX 实现）；`pass` 显示绿色 ✓ 徽标（lucide `Check`）；`fail` 显示红色 ✗ 徽标（lucide `X`）。徽标位于圆圈右上角。
- **测试逻辑**：`src/lib/modelTest.ts` 提供 `testModelConnection(req)` 与 `readModelConfig(slot)`。`readModelConfig(slot)` 优先读取 `localStorage` 用户覆盖；没有用户覆盖时使用 `MODEL_CONFIG_DEFAULTS[slot]`，仅当有效 `baseUrl` / `apiKey` / `modelName` 缺失时返回 `null`，并兼容旧缓存的 `thinkingEnabled` 默认回退。GamePage `testResults: Record<number, ModelTestResult>` 与测试状态提示仅在内存（不写 localStorage）。改 `assignments` 时清除被覆盖 slot 的测试结果。测试中按钮文案显示为「正在测试中」，并至少展示一次可感知的 loading 态；测试完成后每个已分配 slot 必须落成 `pass` 或 `fail`，底部显示通过数量摘要；失败时在摘要下显示模型昵称与后端返回的脱敏短错误。单个 slot 的连通性测试失败后自动按 `1s → 3s → 5s → 10s` 重测，任一尝试成功即落成 `pass`，全部失败才落成 `fail`；取消信号触发后必须立即返回“已取消”，不得继续排队重试。每轮模型连通性测试可在前端为各 slot 记录 UI-only 墙钟耗时（开始偏移、结束偏移、总耗时），并在测试完成后按耗时从慢到快展示诊断表、标记最慢模型；该耗时只用于当前浏览器 UI 诊断，不写 `localStorage`、EventLog、`runs/`、raw response、narrative、SSE、manifest 或 replay hash，也不得包含 API key、provider raw response 或任何后端私有响应。
- **退出流程**：点退出图标 → `ExitConfirmModal`（游戏页自有紧凑确认面板，不复用大厅 `settings_panel_bg.png`；含取消/确认两按钮）→ 确认后调 `onExitGame`（来自 App 层）→ App 反向过渡（600ms 黑屏 → `setPage('lobby')` → 800ms 亮起）。退出后不自动还原 BGM 静音状态；用户可手动取消静音。
- **倒计时**：本步骤暂不实现，留给后续步骤（如需要可由 GamePage 透传一个 `seconds` prop 给后续 `<CountdownBar />`）。
- **DEV-only [debug] 推进按钮**：`import.meta.env.DEV` 守卫；点击 `transitionToStage(...)` 切换白天/黑夜并自增 dayNumber，仅供开发期预览，生产 build tree-shake 掉。
- **网络请求豁免登记**（与 §14.1 "前端不发起 fetch / WebSocket / SSE" 的关系）：
  - **豁免 A — 同源静态资源 fetch**：`RulesModal` 通过 `fetch('/assets/game/rules.md')` 读取打包到 `public/` 的纯文本规则文档。属于浏览器对自身静态资源的请求（与 `<img>` / `<video>` 同性质），不构成跨域 / 后端 / LLM 调用，不破坏 §14.1 边界精神。
  - **豁免 B — 用户主动触发的 LLM 配置自检 fetch**：`testModelConnection` 仅在用户点击"测试模型连通性"按钮时执行；前端只向同源后端 `POST /models/test` 发送 `{provider, model, base_url, api_key, timeout_seconds, thinking_enabled}`，后端临时发起 OpenAI 兼容连通性调用。Qwen 系列始终显式传 `enable_thinking: true/false`；其他模型仅当 `thinkingEnabled === true` 时按模型名追加思考模式字段：`kimi*` / `mimo*` / `deepseek*` / `glm*` / `doubao*` 用 `thinking: {type: "enabled"}`；`hy3*` 用 `chat_template_kwargs: {thinking: true, reasoning_effort: "medium"}`；`MiniMax*` 用 `reasoning_effort: "medium"`。其用途是"配置自检"而非"游戏逻辑驱动"，不构成 PlayerView，不进事件日志，不参与胜负判定；失败只向前端返回脱敏错误摘要。
  - 上述两类 fetch 不允许扩展到游戏逻辑、对局推进、聊天消息收发等任何运行时数据流；引擎相关交互必须等 P2 走 Referee。
  - 风险登记：apiKey 在 fetch header 中明文传输（HTTPS 下加密，HTTP 下泄漏）——文档需提示仅在 HTTPS 部署或本地 dev 使用。CORS 失败由用户感知为席位 ✗，不静默吞错。
