# Prompt Pack

Prompt 模板必须放在语言和角色目录下，并在文件名中携带版本号，例如 `night_action.v6.md`。当前默认中文玩家行动提示词包是 `v6`，也是主仓库内唯一维护的玩家行动 prompt pack。

旧玩家行动 prompt `v1` 到 `v5` 已归档到 `/Users/tampouseng/Desktop/Wolven Hunt 废案/2026-05-29-repo-cleanup/configs/prompts/`，不再参与运行时、replay hash 或默认 resimulate。后续如需考古式恢复旧提示词，应从归档目录按原相对路径放回仓库，并显式指定对应版本。

赛后复盘评审 prompt 版本独立于玩家行动 prompt。真实 provider 主路径使用 `zh/review/global.v1.md` + `zh/review/per_seat.v1.md` 两阶段模板。旧 `zh/review/report.v1.md` 已归档到废案目录，不再作为运行时或测试依赖。

任何 prompt 内容变更都必须检查并同步 `plan.md`；如果变更影响规则、输出 schema、信息边界或 fallback，需要同步更新 `architecture.md`。
