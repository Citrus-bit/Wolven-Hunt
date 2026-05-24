# Prompt Pack

Prompt 模板必须放在语言和角色目录下，并在文件名中携带版本号，例如 `night_action.v1.md`。

当前默认中文提示词包是 `v3`，旧版本文件必须保留用于 replay / resimulate 兼容。任何 prompt 内容变更都必须检查并同步 `plan.md`；如果变更影响规则、输出 schema、信息边界或 fallback，需要同步更新 `architecture.md`。
