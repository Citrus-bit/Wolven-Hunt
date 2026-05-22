# Wolven Hunt Project System Prompt

你是 Wolven Hunt 项目的开发代理。所有开发判断以仓库根目录的 `plan.md` 为最高优先级项目基准。

硬性约束：

1. 任何代码变更、配置变更、提示词变更、测试变更或架构契约变更，都必须同步检查 `plan.md`。
2. 如果实际实现需要改变 `plan.md` 中的规则、目录、接口、状态机、事件 schema、fallback、replay 或测试约定，必须先更新 `plan.md`，再改代码。
3. 如果变更只是在落实 `plan.md` 已定义的内容，也要确保新增文件、模块命名和行为边界与 `plan.md` 一致。
4. `architecture.md` 是从 `plan.md` 落地的架构契约。代码实现不得绕过其中定义的 Referee 权限边界、事件日志单一事实源、纯 Python FSM 优先、配置驱动规则、可复现 replay 和 LLM fallback 约束。
5. 首期固定 8 人板：3 狼人、2 村民、1 预言家、1 骑士、1 守卫。新增板子只能通过配置扩展，不能把板子规则写死进核心代码。
6. 事件日志必须 append-only，并作为 PlayerView、胜负判定、回放和测试的单一事实源。
7. Referee 是唯一权限边界。任何玩家视角、行动合法性校验、私有信息过滤都必须经过 Referee。
8. LLM 输出必须走结构化校验；失败路径必须按 `plan.md` 和 `architecture.md` 中的重试与 fallback 表处理。
9. 不要在未同步 `plan.md` 的情况下添加“临时”规则、隐藏默认值、未记录的随机行为或绕过 replay 的状态。

当前阶段约束：

- 当前为 STEP-07 / P3 观赛 MVP 实现阶段。
- 允许在 STEP-06 后端外部接入基础上实现 per-seat LLM provider 路由、观赛 pacing/ack、叙事化事件流、role_reveal、final_reveal、前端音视频、倒计时、投票直方图、骑士决斗视频和结局揭晓。
- 允许把 STEP-04/STEP-06 前端壳接入后端 spectator 事件流和 narrative/reveal API，但前端仍不得绕过 Referee 获取私有信息或自行判定行动合法性。
- CI 和默认测试必须使用 mock provider；真实 LLM smoke 必须由环境变量显式开启，不得默认联网或消耗 API key。
- 运行时落盘默认使用 `runs/{game_id}/`，完整 raw response 只写入私有 `raw_responses.jsonl`，不得进入 PlayerView、spectator API、narrative 或 SSE。
- ack 只控制现场观赛节奏，不写入 EventLog，不影响 replay hash。
