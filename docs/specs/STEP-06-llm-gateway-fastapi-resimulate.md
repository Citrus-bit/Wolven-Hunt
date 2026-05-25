# STEP-06：LLM 网关 + FastAPI/SSE + replay_resimulate + 前端接入

> **Context**：STEP-05 已交付 P1 后端引擎（GameState / RuleEngine / Referee / FSM / DeterministicMockAgent / 内存 EventLog / `replay_deterministic` / CLI），全部用确定性 mock agent 跑通 100 seed 集成、属性、视角隔离、黄金回归。STEP-06 是 P2：把真实 LLM 接进 PlayerInterface、把 FastAPI/SSE 暴露给外部、把事件与原始响应落盘、补齐 `replay_resimulate`、并把 STEP-04 前端壳打通到后端 spectator 事件流。
>
> plan.md §11 把这一阶段标为 P2；architecture.md §16 把 `replay_resimulate` 显式留到 "STEP-06+"。两份文档把外部边界冻结了，但**没有**写死落盘目录、SSE 线协议、JSON 输出 schema、错误分类映射、resimulate 一致性范围。按 AGENTS.md 硬约束 #2，这些新增边界必须先同步进 plan.md / architecture.md，再落代码——本 spec 第 2 节给出完整同步清单。

硬性约束（节选）：
- 第一阶段固定 8 人板（3 狼 / 2 民 / 1 预言家 / 1 女巫 / 1 守卫）不变；新增板子只能通过 `configs/games/*.yaml` 扩展。
- LLM 输出必须走 Pydantic / JSON Schema 校验；失败路径按 plan.md §4 + 本 spec §5.3 处理。
- 完整 raw response 只进私有存储；`llm_call` 事件只携带 `prompt_hash` / `raw_response_hash` / `storage_ref` / model / token / cost，不进 PlayerView。
- Referee 是唯一权限边界；FastAPI 默认且**仅**返回 spectator 脱敏视角。
- 所有随机决策仍走 `DeterministicRNG`；fallback 随机也必须可由 `random_seed + rng_stream + candidates` 重建。
- 事件日志保持 append-only、单一事实源；`replay_deterministic` 与 `replay_resimulate` 都以 events.jsonl 为输入。
- LLM 测试一律用 mock provider，CI 不消耗 API key、不联网。
- 不修改 `素材/` 目录、不重命名/删除 STEP-04 前端已有文件。

## 1. 交付目标
1. `src/wolven_hunt/llm/` 完整：LiteLLM 网关、prompt 渲染、JSON 输出 schema 与解析、重试循环、成本记录、deterministic mock provider。
2. `LLMAgent` 实现 STEP-05 的 `PlayerInterface` Protocol；FSM 不动即可换入，mock agent 与 LLM agent 在 `agents` dict 中可任意混搭。
3. `src/wolven_hunt/api/` FastAPI 应用：`POST /games`、`GET /games/{id}`、`GET /games/{id}/events`、`GET /games/{id}/stream`（SSE）、`POST /games/{id}/run|pause|resume`、`POST /games/{id}/replay`、`POST /games/{id}/speech`、`POST /games/{id}/wolf_chat`。
4. SSE 线协议冻结：spectator-only，事件 payload = Referee 过滤后的 `Event` JSON + `seq`；30s 心跳；支持 `Last-Event-ID` resume；CORS 白名单可配置。
5. `src/wolven_hunt/storage/disk.py`：每局一目录，包含 `events.jsonl`、`raw_responses.jsonl`、`manifest.json`、`cost.jsonl`，全部原子写（tmp + atomic rename + fsync）。
6. `replay_resimulate(events_path, raw_responses_path) -> tuple[Event, ...]`：以 raw_responses 为 LLM 输入回放 FSM，断言生成事件序列与原 events.jsonl 在 (type, actor, day, phase, canonical-payload) 维度上逐条一致；分歧时给出第一条不匹配的 `(seq, field, expected, actual)`。
7. `cli.py` 新增 `serve` 子命令；现有 `simulate` / `replay` 增加 `--out-dir` 与 `--mode {deterministic,resimulate}`。
8. 前端壳打通（scope B）：`assignments` 页保留模型分配 UI，"开始游戏"按钮改为 `POST /games`；`GameStage` 订阅 SSE 渲染事件时间线；`GameChat` 两个输入框（发言、狼聊）接 `POST /games/{id}/speech` 与 `POST /games/{id}/wolf_chat`；前端不绕过 Referee。
9. plan.md / architecture.md 按 §2 清单同步增补；同步在代码 PR 之前提交，保持 AGENTS.md 硬约束 #2。

## 2. plan.md / architecture.md 同步清单（落代码前先做）
本 STEP 引入的下列条目，plan.md / architecture.md 都没写死。按 AGENTS.md 硬约束 #2，**先把这些条目补进 plan.md（对应小节增补），再镜像进 architecture.md，再开代码 PR**。建议放在 plan.md §3 / §4 / §5 / §9 / §10 现有小节追加而不是另起新章。

| 主题 | plan.md 落点 | architecture.md 镜像 | 必须冻结的内容 |
|---|---|---|---|
| 落盘目录 | §1.1（GameConfig 节附说明）+ 新增 §9.3 | §1 末尾 + §14 模块表 | `runs/{game_id}/{events,raw_responses,cost}.jsonl + manifest.json`，原子写策略，权限位 0600 |
| `llm_call` 事件 schema | §3.3 元数据补字段说明 | §9 | `prompt_hash` / `raw_response_hash` / `storage_ref` / `model` / `prompt_tokens` / `completion_tokens` / `cost_usd` / `prompt_version` 字段类型 |
| LLM 输出 JSON schema（按 phase） | §6.2 后追加表格 | §13 | guard / wolf_chat / wolf_kill / seer / speech / witch / vote / pk_vote / last_words 各自的 Pydantic 模型字段 |
| 错误子类映射到 3 类 | §4.1 表格扩列 | §11 | timeout / rate_limit / network / invalid_json / schema_violation / illegal_action → `agent_timeout` \| `agent_invalid_action` |
| 重试 prompt 增量 | §4.2 | §11 | "重试时附加的错误说明"具体格式 |
| SSE 线协议 | §9.2 `GET /games/{id}/stream` 项展开 | §15 | `event:` 名称、`id:` = seq、`data:` JSON、心跳 `event:heartbeat`、`Last-Event-ID` 语义 |
| FastAPI 错误体 | §9.2 | §15 | `{code, message, details?}` |
| `replay_resimulate` 一致性维度 | §5.2 末尾 | §12 | 比对 `type, actor, day, phase, canonical_payload`；不要求 `event_id` 与 `timestamp` 字节相等 |
| 前端发言 / 狼聊端点 | §9.2 + §14.x | §15 + §18.x | `POST /games/{id}/speech` 与 `POST /games/{id}/wolf_chat` 仍走 Referee `validate_action` |
| LLM 测试边界 | §10.8 增补 | §16 | "CI 一律 mock provider；env-gated 真实模型 smoke 不进默认 pytest" |

落差合规要点：完成上述同步前，禁止合并 STEP-06 任何运行时代码；同步 PR 单独评审一轮。

## 3. Python 工程链增补（在 STEP-05 基础上）
### 3.1 依赖
`pyproject.toml` 追加：`litellm>=1.50`、`fastapi>=0.115`、`uvicorn[standard]>=0.30`、`sse-starlette>=2.1`、`httpx>=0.27`、`pydantic-settings>=2.4`。开发依赖追加：`pytest-asyncio>=0.23`、`asgi-lifespan>=2.1`、`respx>=0.21`（mock LiteLLM 出口 HTTP）。
锁定版本 pin 到具体小版本，遵循 plan.md §1.3。

### 3.2 配置环境变量
新增 `.env.example`（不含真值），列出：`WH_LLM_PROVIDER`、`WH_LLM_API_KEY`、`WH_LLM_BASE_URL`、`WH_LLM_TIMEOUT_SECONDS`、`WH_LLM_MAX_RETRIES`、`WH_LLM_BUDGET_PER_GAME`、`WH_RUNS_DIR`、`WH_API_HOST`、`WH_API_PORT`、`WH_API_CORS_ORIGINS`。`.env` 已在 `.gitignore`。
通过 `pydantic-settings.BaseSettings` 读入，禁止在模块顶层 `os.getenv`；统一封装在 `src/wolven_hunt/config/settings.py`。

### 3.3 Makefile 目标追加
`make serve`（启 uvicorn dev）、`make test-llm`（跑 LLM mock 测试子集）、`make resimulate FILE=...`。

## 4. 模块结构（仅列新增 / 改动）
```
src/wolven_hunt/
  llm/
    __init__.py
    gateway.py          # LLMGateway: 单次调用（含超时、重试、错误归类、成本累加）
    provider.py         # LiteLLM provider 适配；mock provider 同接口
    schemas.py          # 9 个 phase 的 Pydantic 输出模型
    prompts.py          # PromptRenderer：PlayerView -> 文本；prompt_version 注入
    cost.py             # CostTracker：per-game token + cost 累计与上限断言
  agents/
    llm_agent.py        # LLMAgent(seat, gateway, prompt_pack)；实现 PlayerInterface
  api/
    __init__.py
    app.py              # FastAPI app 工厂
    routes_games.py     # /games 系列端点
    sse.py              # SSE 流封装；resume + 心跳
    schemas.py          # 请求 / 响应 Pydantic 模型
    deps.py             # 依赖注入（GameRegistry、Settings）
  orchestration/
    runtime.py          # GameRegistry：内存中按 game_id 管理一局 + 事件总线
  storage/
    disk.py             # write_events_jsonl / write_raw_response / write_manifest（atomic）
    replay.py           # 在原文件中加 replay_resimulate
  cli.py                # 新增 serve 子命令；simulate 增加 --out-dir
```

测试树新增：
```
tests/
  unit/
    test_llm_schemas.py
    test_llm_gateway_retry.py
    test_cost_tracker.py
    test_disk_atomic_write.py
  integration/
    test_llm_agent_full_loop.py    # 用 mock provider 跑通 100 seed
    test_resimulate_consistency.py # 落盘后用 raw_responses 重跑事件序列一致
    test_api_games.py              # ASGI 客户端走完 POST /games -> events
    test_sse_stream.py             # 心跳 + Last-Event-ID resume
  property/
    test_llm_invariants.py         # hypothesis：任意 mock 响应下不变量保持
  leakage/
    test_sse_spectator_only.py     # SSE 流只含 spectator 视角事件
```

## 5. 关键契约
### 5.1 PlayerInterface 不变
`LLMAgent` 实现 STEP-05 的 9 个 `decide_*` 方法。每个方法内部：渲染 prompt → `gateway.call(...)` → Pydantic 解析 → 返回 `Action` 子类。校验失败抛 `LLMValidationError`，由 FSM 现有 `_decide_with_fallback` 触发 fallback（无需改 FSM）。

### 5.2 LLMGateway.call
签名：
```python
def call(
    self,
    *,
    seat: Seat,
    phase: str,
    prompt: str,
    output_model: type[BaseModel],
    rng: DeterministicRNG,  # 仅用于 fallback / mock，真实调用不消费
) -> LLMCallResult: ...
```
`LLMCallResult` 含：`parsed`（输出模型实例 | None）、`raw_response`、`prompt_hash`、`raw_response_hash`、`storage_ref`、`model`、`tokens`、`cost_usd`、`error`（None | `LLMError`）。

### 5.3 重试 + fallback（落 plan §4.1–§4.3）
1. 单次调用：超时 = `WH_LLM_TIMEOUT_SECONDS`（默认 30s）；超时 / RateLimit / Network / InvalidJSON / SchemaViolation 都计入"重试预算"。
2. 最多 `WH_LLM_MAX_RETRIES`（默认 4）次重试，重试 prompt 末尾追加错误说明（仅本人可见）。
3. 重试耗尽 → `LLMAgent` 抛 `LLMFallbackRequired`；`_decide_with_fallback` 触发现有 fallback 路径并发出 `agent_fallback_triggered` 事件。
4. 错误子类到事件类型的映射写在 plan.md §4.1（本 spec §2 已列），`agent_timeout` 与 `agent_invalid_action` 是仅有的两类外显事件。

### 5.4 落盘契约
目录布局：
```
{WH_RUNS_DIR}/{game_id}/
  manifest.json        # config_hash, seed, prompt_pack_version, started_at, ended_at, winner
  events.jsonl         # 与 EventLog.events 一一对应（含全部可见性）
  raw_responses.jsonl  # 每行 {storage_ref, seat, phase, day, seq, model, prompt_hash, raw_response_hash, raw_response, prompt_tokens, completion_tokens, cost_usd}
  cost.jsonl           # 每行单次调用的 token / cost 流水
```
原子写：`tmp` 文件追加 + `os.fsync` + `os.replace`；events.jsonl 使用 append-only 追加 + 行级 fsync，进程崩溃后恢复时按最后一行的 `seq` 截断。文件权限 0600。

### 5.5 replay_resimulate
入参：`events_path: Path`、`raw_responses_path: Path`。流程：
1. 从 events.jsonl 读出 `seed` 与 `config_hash`，加载对应 `GameConfig`。
2. 用 `seed` 重建初始 `GameState`，构造一个 `ReplayLLMProvider`：按 `(seat, day, phase, seq)` 复用 raw_responses.jsonl 的原始字符串，跳过真实网络。
3. 跑 `run_game(...)` 得到新的事件序列。
4. 在 `(type, actor, day, phase, canonical_payload)` 维度上逐条比对；首个分歧返回 `ResimulateDivergence(seq, field, expected, actual)`。
5. 一致则返回新事件元组。
注意：不要求 `event_id`、`timestamp` 字节级相等（plan §2 同步条目已冻结此豁免）。

### 5.6 FastAPI 表面
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/games` | body: `{config_path, seed, agents: {seat: "mock"\|"llm:<roster_key>"}}`；返回 `{game_id}` |
| GET  | `/games/{id}` | spectator 当前状态摘要 |
| GET  | `/games/{id}/events` | 历史事件 JSON 数组（spectator 过滤） |
| GET  | `/games/{id}/stream` | SSE 流；支持 `Last-Event-ID` |
| POST | `/games/{id}/run` \| `/pause` \| `/resume` | 流程控制 |
| POST | `/games/{id}/replay` | body: `{mode: "deterministic"\|"resimulate"}` |
| POST | `/games/{id}/speech` | body: `{seat, text}`；走 Referee `validate_action` |
| POST | `/games/{id}/wolf_chat` | 同上，仅当 actor 为狼 |

错误体：`{code: str, message: str, details?: object}`；HTTP 状态码 4xx 走业务校验失败、5xx 走系统错误。

### 5.7 SSE 线协议
- `event: game_event`
- `id: <seq>`
- `data: <Event JSON, spectator 过滤后>`
- 每 30s 发 `event: heartbeat\ndata: {}`
- 客户端断线重连时携带 `Last-Event-ID: <seq>`，服务端从 `seq+1` 续推；不存在则关闭连接并返回 410。
- CORS：默认 `http://localhost:5173`，`WH_API_CORS_ORIGINS` 可配置。

### 5.8 前端接入（scope B）
- `src/state/GameContext.tsx`（已存在）追加 `gameId: string | null`、`events: Event[]`、`subscribeStream(gameId)`。
- `src/components/GameStart/StartGameButton.tsx` 改为 `POST /games`，成功后调 `subscribeStream`。
- `src/components/Game/GameStage.tsx` 用 `events` 渲染时间线（替换现 mock 数据）。
- `src/components/Game/GameChat.tsx` 解禁两个输入框，按当前阶段路由到 `POST /games/{id}/speech` 或 `/wolf_chat`。
- 前端不解析私有事件；spectator 流不会出现 wolf_chat / seer 私有事件，前端因此不需要任何过滤逻辑——保留"前端不绕过 Referee"硬约束。
- 不动 `素材/`、不重命名/删除 STEP-04 已交付组件。

## 6. 修改清单
| 文件 | 操作 | 说明 |
|---|---|---|
| `plan.md` | 改 | 按本 spec §2 增补 10 条契约（先行 PR） |
| `architecture.md` | 改 | 镜像同步上述 10 条 |
| `pyproject.toml` | 改 | 追加运行时与开发依赖；不动已 pin 版本 |
| `Makefile` | 改 | 追加 serve / test-llm / resimulate 目标 |
| `.env.example` | 新增 | 列出全部 WH_ 前缀环境变量 |
| `src/wolven_hunt/config/settings.py` | 新增 | `Settings(BaseSettings)` |
| `src/wolven_hunt/llm/{gateway,provider,schemas,prompts,cost}.py` | 新增 | LLM 网关全栈 |
| `src/wolven_hunt/agents/llm_agent.py` | 新增 | 实现 PlayerInterface |
| `src/wolven_hunt/api/{app,routes_games,sse,schemas,deps}.py` | 新增 | FastAPI 表面 |
| `src/wolven_hunt/orchestration/runtime.py` | 新增 | GameRegistry + 事件总线 |
| `src/wolven_hunt/storage/disk.py` | 新增 | 原子写工具 |
| `src/wolven_hunt/storage/replay.py` | 改 | 追加 `replay_resimulate` |
| `src/wolven_hunt/cli.py` | 改 | 追加 `serve`，`simulate` 加 `--out-dir`、`--mode` |
| `configs/models/providers.yaml` | 改 | 把 mock provider 列为默认；真实 provider 可选 |
| `configs/models/roster.yaml` | 改 | 8 座位 → model alias 映射 |
| `configs/prompts/zh/<role>/<phase>.v1.md` | 新增 | 9 个 phase × 多角色提示词，附 `prompt_version` |
| `src/state/GameContext.tsx` | 改 | 加 gameId / events / SSE 订阅 |
| `src/components/GameStart/*.tsx` | 改 | 启动按钮调 POST /games |
| `src/components/Game/GameStage.tsx` | 改 | 渲染真实事件流 |
| `src/components/Game/GameChat.tsx` | 改 | 解禁输入框，接 speech / wolf_chat |
| `tests/**` | 新增 | 见 §4 测试树 |

## 7. 实施顺序
1. **plan/architecture 同步 PR**（必须先 merge）：按 §2 清单把 10 条契约写进文档。
2. 工程链：依赖、Makefile、.env.example、Settings。
3. LLM 层：schemas → prompts → mock provider → gateway（含重试 / 错误归类 / cost）。
4. LLMAgent：在 mock provider 下跑通 100 seed 集成。
5. 落盘层：disk.py 原子写；EventLog 增"持久化 sink"挂钩；cost.jsonl + manifest.json。
6. replay_resimulate：实现 + 一致性测试。
7. FastAPI：app + routes + SSE + GameRegistry；ASGI 测试覆盖。
8. CLI `serve`、`simulate --out-dir`、`replay --mode`。
9. 前端接入（scope B）：GameContext → StartGameButton → GameStage → GameChat。
10. 端到端冒烟：前端启动一局 → SSE 事件 → 发言提交 → events.jsonl 落盘 → resimulate 一致。

## 8. 验收指标

### A. plan / architecture 同步
| ID | 检查项 | 验证手段 |
|---|---|---|
| A1 | plan.md §2 列的 10 条契约全部落地（落盘目录 / llm_call schema / 输出 schema / 错误映射 / 重试增量 / SSE / FastAPI 错误体 / resimulate 维度 / speech & wolf_chat 端点 / LLM 测试边界） | `grep -n` 关键词在 plan.md / architecture.md 都命中 |
| A2 | 同步 PR 在代码 PR 之前 merge | `git log --oneline` 检查 commit 顺序 |
| A3 | architecture.md 镜像与 plan.md 表述等价 | 人工对照 §2 表格 |

### B. LLM 网关
| ID | 检查项 | 验证手段 |
|---|---|---|
| B1 | LLMGateway 调用 mock provider 完成 100 seed × 8 座位无未捕获异常 | `pytest tests/integration/test_llm_agent_full_loop.py -q` |
| B2 | 9 个 phase 的 Pydantic 输出模型全部存在并被 prompts 引用 | `grep -rn "output_model=" src/wolven_hunt/agents/llm_agent.py` 命中 9 处 |
| B3 | 错误子类映射符合 plan.md §4.1：timeout/network/rate_limit → `agent_timeout`；invalid_json/schema/illegal → `agent_invalid_action` | `pytest tests/unit/test_llm_gateway_retry.py -q` 覆盖 6 子类 |
| B4 | 重试预算 = 配置值；耗尽即触发 fallback 并发 `agent_fallback_triggered` | 同上 |
| B5 | `llm_call` 事件 payload 含 `prompt_hash` / `raw_response_hash` / `storage_ref` / `model` / `tokens` / `cost_usd` / `prompt_version`，**不**含 `raw_response` 原文 | `pytest tests/leakage/test_sse_spectator_only.py` + 直接断言 |
| B6 | CostTracker 超 `WH_LLM_BUDGET_PER_GAME` 触发告警事件但不中止 | unit 测试 |

### C. 落盘存储
| ID | 检查项 | 验证手段 |
|---|---|---|
| C1 | 一局结束后 `runs/{game_id}/` 包含 `events.jsonl` / `raw_responses.jsonl` / `manifest.json` / `cost.jsonl` 四件套 | `ls runs/<id>/` |
| C2 | events.jsonl 行数 = `len(EventLog.events)` | `wc -l` 比对 |
| C3 | raw_responses.jsonl 行数 = `agent_*` 调用次数（含重试） | 测试断言 |
| C4 | 文件权限 0600 | `stat -f '%Mp%Lp'`（macOS）或 unit 测试 |
| C5 | 原子写：进程在写入中被 SIGKILL 不残留半行 | `pytest tests/unit/test_disk_atomic_write.py` |
| C6 | manifest.json 含 `config_hash` / `seed` / `prompt_pack_version` / `started_at` / `ended_at` / `winner` | unit 测试 |

### D. replay_resimulate
| ID | 检查项 | 验证手段 |
|---|---|---|
| D1 | 同一局 `replay_resimulate` 在 `(type, actor, day, phase, canonical_payload)` 维度逐条匹配原 events.jsonl | `pytest tests/integration/test_resimulate_consistency.py` |
| D2 | 篡改 raw_responses.jsonl 任一行（改 wolf 投票目标）后 resimulate 报告 `ResimulateDivergence(seq, "payload.target", ...)` | 同上 |
| D3 | resimulate 不发起任何外部 HTTP（用 `respx` 拦截后断言无请求） | 同上 |
| D4 | 100 seed × deterministic 模式：`replay_deterministic == replay_resimulate == 原 events`（mock 路径下三者等价） | 集成测试 |

### E. FastAPI
| ID | 检查项 | 验证手段 |
|---|---|---|
| E1 | `POST /games` 接受 `{config_path, seed, agents}`，返回 `{game_id}` | `pytest tests/integration/test_api_games.py` |
| E2 | `GET /games/{id}/events` 默认返回 spectator 过滤后的事件 | 同上 |
| E3 | 不存在的 game_id → 404 + `{code:"game_not_found"}` | 同上 |
| E4 | `POST /games/{id}/speech` 在非 DAY_SPEECH / 非 actor 存活时 → 422 + Reject.rule_id | 同上 |
| E5 | `POST /games/{id}/wolf_chat` 非狼 / 非夜聊阶段 → 422 | 同上 |
| E6 | 所有响应不含 `seer_check_result` / `wolf_chat_message` / `llm_call` 三类私有事件 | leakage 测试 |

### F. SSE
| ID | 检查项 | 验证手段 |
|---|---|---|
| F1 | `GET /games/{id}/stream` 推送的 `id:` 严格单调递增 | `pytest tests/integration/test_sse_stream.py` |
| F2 | 30s 内至少出现一次 `event: heartbeat`（测试用快速时钟） | 同上 |
| F3 | `Last-Event-ID: 5` 续推从 seq=6 开始 | 同上 |
| F4 | 不在 spectator 视角的事件不会出现在流里 | leakage 测试 |
| F5 | 客户端断开后服务端释放任务（无僵尸协程） | asgi-lifespan 断言 |

### G. 前端接入
| ID | 检查项 | 验证手段 |
|---|---|---|
| G1 | `assignments` 页"开始游戏"成功调 `POST /games` 并跳转 GameStage | 浏览器手测 + 后端日志 |
| G2 | GameStage 显示后端推送的真实事件（白天死亡、投票结果、放逐） | 浏览器手测 |
| G3 | GameChat 发言输入框在 DAY_SPEECH 阶段可用，提交后 1s 内出现在事件流 | 浏览器手测 |
| G4 | 狼聊输入框只在玩家为狼且 NIGHT_WOLF_CHAT 阶段可用 | 浏览器手测；非狼座位不可见 |
| G5 | 前端代码无对私有事件的解析（grep `seer_check_result` 仅出现在类型定义） | `grep -rn "seer_check_result\|wolf_chat_message" src/` |
| G6 | STEP-04 已有页面（assignments 模型分配 UI、规则模态、底部操作）行为不退化 | 手测 + 现有截图回归 |

### H. 测试与 CI
| ID | 检查项 | 验证手段 |
|---|---|---|
| H1 | `pytest -q` 全绿，新增测试包含：unit (4) + integration (4) + property (1) + leakage (1) | 输出统计 |
| H2 | CI 不联网；`respx` 断言无未拦截 HTTP 请求 | CI 日志 |
| H3 | `make test-llm` 单跑 LLM 子集 < 30s | 实测 |
| H4 | mypy strict 0 错误，ruff check + format 通过 | `make check` |
| H5 | 100 seed × LLM mock × 落盘 × resimulate 端到端 < 60s | `pytest tests/integration -q` |

### I. 边界与硬约束
| ID | 检查项 | 验证手段 |
|---|---|---|
| I1 | `llm_call` 事件不含 raw_response 原文 | grep + 测试 |
| I2 | spectator SSE 流不泄露 wolf_chat / seer / guard / llm_call | leakage 测试 |
| I3 | FastAPI 路由处理函数中无对 `state.players` 的私有字段读取，全部走 Referee | 代码评审 + grep |
| I4 | LLM 调用的所有错误归一化到 plan.md §4.1 三类，不出现新的事件类型 | grep `EventType.` 新增项与 plan §3.3 比对 |
| I5 | 真实 LLM 调用环境变量缺失时启动会失败而非默默降级 | unit 测试 |
| I6 | 8 人板配置仍然是默认；新增 board 必须经 `configs/games/*.yaml` | grep 没有新写死的 8 / 板规则 |

## 9. 不在本步骤范围
- per-seat 视角 SSE（推迟到"人类玩家入座"阶段）。
- 多局并发 / 跨进程调度 / Redis 队列。
- 真实 model 集成的默认 CI 验证（仅留 env-gated smoke）。
- 用户系统 / 鉴权 / 多租户。
- prompt A/B、自动评测、对局录像渲染前端可视化。
- 前端历史对局列表 / 回放页面（`POST /games/{id}/replay` 后端先具备能力，前端 UI 留给下一步）。
- 把 STEP-05 mock agent 替换为 LLM agent 的默认配置——CI 默认仍跑 mock。

## 10. 风险登记
- **plan/architecture 同步漂移**：若实现 PR 抢跑同步 PR，会破坏 AGENTS.md 硬约束 #2。缓解：在 PR 模板里加一条"是否已落 plan.md / architecture.md"勾选项；§7 实施顺序硬性 1 在前。
- **私有事件经 SSE 泄漏**：FastAPI 路由如果直接序列化 `EventLog.events` 而不过 Referee，会把 `seer_check_result` / `wolf_chat_message` / `llm_call` 推到前端。缓解：`sse.py` 只接收 `build_view(seat=None)` 的输出，且加 leakage 测试 I2。
- **LiteLLM 出口非确定性**：真实 provider 流式 / 重试时序可能影响 cost.jsonl 顺序。缓解：cost 以 `(seq_of_llm_call_event, attempt_no)` 主键，不靠时间戳。
- **resimulate 与 RNG 漂移**：FSM 在 fallback 路径上消费 RNG；若 raw_responses 改了某次响应，会触发不同 fallback 分支并消耗不同 RNG stream，后续随机决策跟着漂。缓解：D2 测试覆盖；resimulate 报告必须标记首个分歧的 `seq`。
- **JSONL 行损坏**：append 写入崩溃可能留半行。缓解：每行写完即 `fsync`；恢复时按"末行解析失败则截断到上一行"策略；C5 测试覆盖。
- **前端 SSE 兼容性**：原生 EventSource 不发自定义 header；`Last-Event-ID` 由浏览器自动维护，但跨域时需 `withCredentials` 与 CORS 协同。缓解：`WH_API_CORS_ORIGINS` 显式白名单 + 测试覆盖。
- **环境变量遗漏导致默默走 mock**：生产希望真实 LLM，开发希望 mock，配错可能"看起来正常"。缓解：`Settings` 校验 `WH_LLM_PROVIDER ∈ {mock, litellm}`，缺失或非法即启动失败（I5）。
- **prompt_version 漂移**：改 prompt 文件而忘了 bump 版本会让旧日志解释失真。缓解：`prompts.py` 启动时校验文件名版本号与 `manifest.json` 中 `prompt_pack_version` 一致；CI 加 grep 检查。

## 11. 验证方法（端到端）
```bash
# 1. 同步 PR 已合并
grep -n "raw_response_hash" plan.md architecture.md
grep -n "Last-Event-ID" plan.md architecture.md

# 2. 后端冒烟
make check && pytest -q
make serve &
curl -X POST localhost:8000/games -d '{"config_path":"configs/games/classic_8.yaml","seed":"smoke-001","agents":{"1":"llm:default", "...":"..."}}'
curl -N localhost:8000/games/<id>/stream | head -20
ls runs/<id>/

# 3. resimulate
python -m wolven_hunt resimulate --events runs/<id>/events.jsonl --raw runs/<id>/raw_responses.jsonl

# 4. 前端冒烟
pnpm dev
# 浏览器：assignments → 开始游戏 → 看到事件时间线滚动 → 在 DAY_SPEECH 提交一句发言 → 出现在时间线
```


