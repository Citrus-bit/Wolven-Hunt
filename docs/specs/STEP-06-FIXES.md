# STEP-06 收尾修改单

> **Context**：STEP-06 初版已交付，验收发现 5 条硬伤需要回炉。本修改单按优先级排序，每条给出当前问题、期望行为、具体修改点、验收标准。修完后重跑验收指标 B6 / F2 / F5 / G4 / H4 + 端到端冒烟。

## 修改优先级与依赖
1. **H4 ruff format**（最简单，先做）
2. **WH_LLM_* 文档同步**（合规修复，独立）
3. **F2 live-game + SSE 心跳**（最重要，改动最大，影响 G3/G4/F5）
4. **B6 CostTracker 事件**（独立）
5. **G4 wolf chat 守卫**（依赖 F2 修完后端到端才能测）

---

## 1. H4 — ruff format 失败 4 文件

### 当前问题
`uv run ruff format --check src tests` 报告 4 文件需要重新格式化：
- `src/wolven_hunt/api/routes_games.py`
- `src/wolven_hunt/llm/provider.py`
- `src/wolven_hunt/storage/replay.py`
- `tests/unit/test_disk_atomic_write.py`

### 期望行为
`make check` 全绿，包括 `ruff format --check` 通过。

### 修改步骤
```bash
cd "/Users/tampouseng/Desktop/Wolven Hunt"
uv run ruff format src tests
git add -u
git commit -m "style: apply ruff format to 4 files"
```

### 验收
```bash
uv run ruff format --check src tests
# 输出：All files formatted.
make check
# 输出：全绿
```

---

## 2. WH_LLM_* 环境变量同步进 plan.md / architecture.md

### 当前问题
STEP-06 spec §3.2 列出 11 个 `WH_*` 环境变量，但 plan.md / architecture.md 都没记录。违反 AGENTS.md 硬约束 #2（新增边界必须先同步文档再落代码）。

### 期望行为
plan.md §9.1 末尾、architecture.md §15 配置段各补一段环境变量清单。

### 修改点

**plan.md** — 在 §9.1 "LLM 网关" 末尾（当前约 line 460 附近）追加：

```markdown
#### 环境变量

STEP-06 引入以下环境变量（通过 `pydantic-settings.BaseSettings` 读入，封装在 `src/wolven_hunt/config/settings.py`）：

- `WH_LLM_PROVIDER`：`mock` | `litellm`，必填；缺失或非法值启动失败
- `WH_LLM_API_KEY`：真实 provider 的 API key；`WH_LLM_PROVIDER=litellm` 时必填
- `WH_LLM_BASE_URL`：LiteLLM base URL，可选
- `WH_LLM_MODEL`：默认模型名，可选（roster.yaml 可覆盖）
- `WH_LLM_TIMEOUT_SECONDS`：单次调用超时，默认 30
- `WH_LLM_MAX_RETRIES`：重试预算，默认 4；已加载 RuleSet 的 `fallback.max_retries` 优先
- `WH_LLM_BUDGET_PER_GAME`：单局 token 上限，默认 100000
- `WH_RUNS_DIR`：落盘根目录，默认 `./runs`
- `WH_API_HOST`：FastAPI 监听地址，默认 `0.0.0.0`
- `WH_API_PORT`：FastAPI 监听端口，默认 8000
- `WH_API_CORS_ORIGINS`：CORS 白名单，逗号分隔，默认 `http://localhost:5173`

`.env` 已在 `.gitignore`；`.env.example` 列出全部变量（不含真值）。CI 使用 `WH_LLM_PROVIDER=mock`，不消耗 API key。
```

**architecture.md** — 在 §15 "FastAPI 接口（P2）" 末尾（当前约 line 365 附近）追加相同内容（或简化为"环境变量清单见 plan.md §9.1"）。

### 验收
```bash
grep -n "WH_LLM_PROVIDER" plan.md architecture.md
# 两个文件都命中
grep -n "WH_API_CORS_ORIGINS" plan.md architecture.md
# 两个文件都命中
```

---

## 3. F2 — SSE 心跳 + live-game 语义（最重要）

### 当前问题
1. `src/wolven_hunt/orchestration/runtime.py::create_game` **同步**跑完整局再返回 `game_id`，意味着前端打开 `GET /games/{id}/stream` 时一局已结束。
2. `POST /games/{id}/speech` 与 `/wolf_chat` 在已结束的局里被 Referee 422 拒绝（phase 不匹配）。
3. `src/wolven_hunt/api/sse.py::stream_game_events` 把缓冲事件 drain 完后只发**一次** end-of-stream heartbeat，不是周期性 30s 心跳。

### 期望行为
- `create_game` 启动异步任务跑引擎，立即返回 `game_id`；引擎边跑边写事件到 `asyncio.Queue`。
- SSE generator 从 queue 消费事件，30s 内无新事件则发 `event: heartbeat`。
- `/speech` 与 `/wolf_chat` 在游戏进行中能提交成功，1s 内出现在 SSE 流。
- `/pause` / `/resume` 能真正暂停/恢复引擎。

### 修改点

#### 3.1 `src/wolven_hunt/orchestration/runtime.py`

**当前设计**：`GameSession` 持有 `state` + `event_log`，`create_game` 同步调 `run_game` 跑完。

**改为**：
1. `GameSession` 增加 `event_queue: asyncio.Queue[Event]`、`task: asyncio.Task | None`、`paused: bool`。
2. `create_game` 改为：
   ```python
   async def create_game(self, config: GameConfig, seed: str, agents: AgentMap) -> str:
       game_id = GameId.deterministic(seed)
       session = GameSession(...)
       session.event_queue = asyncio.Queue()
       session.task = asyncio.create_task(self._run_game_async(session, config, seed, agents))
       self._sessions[game_id] = session
       return str(game_id)
   ```
3. 新增 `_run_game_async`：
   ```python
   async def _run_game_async(self, session: GameSession, config: GameConfig, seed: str, agents: AgentMap) -> None:
       # 在后台线程跑 run_game（因为 run_game 是同步的），每产生一个事件就 await session.event_queue.put(event)
       # 或者：把 orchestration/fsm.py::run_game 改成 async，每次 event_log.append 后 await queue.put
       # 推荐后者，但改动更大；前者用 asyncio.to_thread 包 run_game，定期轮询 event_log 新增
       ...
   ```
4. `pause_game` / `resume_game` 设置 `session.paused`，`_run_game_async` 在每个 phase 开始前检查。

#### 3.2 `src/wolven_hunt/api/sse.py`

**当前**：`stream_game_events` 从 `session.spectator_events()` 拿到已完成的事件列表，drain 后发一次心跳。

**改为**：
```python
async def stream_game_events(session: GameSession, start_after: int) -> AsyncGenerator[str, None]:
    seq = start_after
    while True:
        try:
            event = await asyncio.wait_for(session.event_queue.get(), timeout=30.0)
            if event.seq > seq:
                seq = event.seq
                # 过 Referee 过滤
                filtered = build_view(session.state, (event,), rule_set=..., seat=None).visible_events
                if filtered:
                    yield _format_event(filtered[0])
        except asyncio.TimeoutError:
            yield "event: heartbeat\ndata: {}\n\n"
        
        # 检查游戏是否结束
        if session.state.winner is not None and session.event_queue.empty():
            break
```

**注意**：`session.event_queue` 需要在 `_run_game_async` 里每产生一个事件就 `put`；`build_view` 需要能处理单个事件（或者在 queue 里放已过滤的事件）。

#### 3.3 `src/wolven_hunt/api/routes_games.py`

- `POST /games` 改为 `await registry.create_game(...)`（如果 `create_game` 改成 async）。
- `POST /games/{id}/speech` 与 `/wolf_chat` 改为：提交 action → `session.pending_actions.put(action)` → `_run_game_async` 在合适的 phase 消费 `pending_actions`。

**或者更简单的方案**（推荐）：
- 保持 `run_game` 同步，但在 `asyncio.to_thread` 里跑；每次 `event_log.append` 后通过 `call_soon_threadsafe` 把事件 put 进 queue。
- `/speech` 与 `/wolf_chat` 直接调 `apply_action` + `event_log.append` + `queue.put`，不走 FSM 主循环（因为 FSM 在后台线程）。这需要加锁保护 `state` 与 `event_log`。

### 验收
```bash
# 1. 启动后端
make serve &

# 2. 创建一局（应该立即返回 game_id，不等游戏跑完）
curl -X POST http://localhost:8000/games -H "Content-Type: application/json" \
  -d '{"config_path":"configs/games/classic_8.yaml","seed":"live-001","agents":{"1":"mock","2":"mock","3":"mock","4":"mock","5":"mock","6":"mock","7":"mock","8":"mock"}}'
# 输出：{"game_id":"..."}

# 3. 立即打开 SSE 流（应该能看到事件逐条推送，30s 内无事件时出现 heartbeat）
curl -N http://localhost:8000/games/<game_id>/stream

# 4. 在另一个终端，等游戏进入 DAY_SPEECH 阶段后提交发言
curl -X POST http://localhost:8000/games/<game_id>/speech -H "Content-Type: application/json" \
  -d '{"seat":1,"text":"测试发言"}'
# 输出：200 OK
# SSE 流应该在 1s 内出现 SPEECH 事件

# 5. 前端冒烟：浏览器打开 http://localhost:5173，assignments → 开始游戏 → 看到事件时间线滚动 → 在 DAY_SPEECH 提交发言 → 出现在时间线
```

---

## 4. B6 — CostTracker 不发 over-budget 事件

### 当前问题
`src/wolven_hunt/llm/cost.py::CostTracker.over_budget` 只是一个 property，没有事件通道。spec §10.7 + B6 要求超预算时**发告警事件但不中止**。

### 期望行为
- `LLMGateway.call` 累加 cost 后判断 `tracker.over_budget`，首次超限时发一次 `AGENT_BUDGET_WARNING` 事件（或复用现有 system event 类型）。
- 游戏继续跑，不中止。
- 有 unit 测试覆盖。

### 修改点

#### 4.1 确认事件类型
检查 `src/wolven_hunt/core/events.py::EventType` 是否已有 `AGENT_BUDGET_WARNING`。如果没有，需要：
1. 在 `EventType` 增加 `AGENT_BUDGET_WARNING = "agent_budget_warning"`。
2. 同步进 plan.md §3.3 和 architecture.md §9 的事件类型表。

#### 4.2 `src/wolven_hunt/llm/gateway.py`
在 `LLMGateway.call` 返回前（或 `orchestration/fsm.py::_decide_with_fallback` 拿到 `LLMCallResult` 后）：
```python
if cost_tracker.over_budget and not cost_tracker._warning_emitted:
    cost_tracker._warning_emitted = True  # 只发一次
    event_log.append(
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.AGENT_BUDGET_WARNING,
            actor=None,
            visibility=public_visibility(),
            payload={
                "budget": cost_tracker.budget,
                "used": cost_tracker.total_cost,
                "message": f"Token budget exceeded: {cost_tracker.total_cost:.4f} > {cost_tracker.budget}",
            },
        )
    )
```

#### 4.3 `src/wolven_hunt/llm/cost.py`
给 `CostTracker` 加一个 `_warning_emitted: bool = False` 字段（或者在 `GameSession` 里记录）。

#### 4.4 测试
新增 `tests/unit/test_cost_tracker.py::test_over_budget_emits_warning_once`：
```python
def test_over_budget_emits_warning_once():
    tracker = CostTracker(budget=100.0)
    tracker.add(prompt_tokens=1000, completion_tokens=1000, cost_usd=50.0)
    assert not tracker.over_budget
    tracker.add(prompt_tokens=2000, completion_tokens=2000, cost_usd=60.0)
    assert tracker.over_budget
    # 模拟 FSM 发事件逻辑，断言只发一次
```

### 验收
```bash
uv run pytest tests/unit/test_cost_tracker.py -v -k over_budget
# 输出：test_over_budget_emits_warning_once PASSED
```

---

## 5. G4 — wolf chat 输入无 phase / role 守卫

### 当前问题
`src/components/Game/GameChat.tsx` 的狼聊输入只要 `gameId` 非空就启用。后端 Referee 会 422 拒绝非狼座位或非 `NIGHT_WOLF_CHAT` 阶段的提交，但 UX 让非狼座位看到能输入的框。spec §5.8 + G4 要求条件渲染。

### 期望行为
- 狼聊 section 只在 `phase === 'NIGHT_WOLF_CHAT' && isWolfSeat` 时渲染（或输入框 disabled + 显示阶段提示）。
- `isWolfSeat` 来自后端，但 spectator 视角不暴露身份——需要新增端点或在 `GET /games/{id}` 返回当前 seat 角色（仅当前端以某个 seat 身份订阅时）。

### 修改点（推荐方案：disabled + 提示）

#### 5.1 前端 `src/components/Game/GameChat.tsx`
不新增后端端点，保持"前端不绕过 Referee"。改为：
```tsx
// 狼聊输入框始终渲染，但根据 phase 条件 disabled
<input
  disabled={!gameId || phase !== 'NIGHT_WOLF_CHAT' || isSubmitting}
  placeholder={phase === 'NIGHT_WOLF_CHAT' ? '狼人夜聊' : '仅狼人夜聊阶段可用'}
  ...
/>
```

`phase` 从哪来？
- 方案 A：`GET /games/{id}` 返回 `current_phase`（spectator 可见）。
- 方案 B：SSE 事件里带 `phase` 字段，前端从最新事件推断当前阶段。

推荐方案 A，在 `src/wolven_hunt/api/routes_games.py::get_game` 返回体里加 `phase: state.phase`。

#### 5.2 后端 `src/wolven_hunt/api/routes_games.py`
```python
@router.get("/games/{game_id}")
async def get_game(game_id: str, registry: GameRegistry = Depends(get_registry)):
    session = registry.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "game_not_found"})
    return {
        "game_id": game_id,
        "phase": session.state.phase,
        "day": session.state.day,
        "winner": session.state.winner.value if session.state.winner else None,
        "alive_seats": [seat.number for seat in session.state.alive_seats()],
    }
```

#### 5.3 前端 `src/lib/gameApi.ts` + `GamePage.tsx`
- `gameApi.ts` 增加 `getGame(gameId)` 调用 `GET /games/{id}`。
- `GamePage.tsx` 定期轮询或从 SSE 事件推断 `phase`，传给 `<GameChat phase={phase} />`。

### 验收
```bash
# 浏览器手测：
# 1. 打开前端，开始一局
# 2. 在非 NIGHT_WOLF_CHAT 阶段，狼聊输入框应该 disabled，placeholder 显示"仅狼人夜聊阶段可用"
# 3. 进入 NIGHT_WOLF_CHAT 阶段，输入框启用，placeholder 显示"狼人夜聊"
```

---

## 实施顺序总结
1. H4 ruff format（1 分钟）
2. WH_LLM_* 文档同步（5 分钟）
3. F2 live-game + SSE 心跳（1–2 小时，最复杂）
4. B6 CostTracker 事件（30 分钟）
5. G4 wolf chat 守卫（30 分钟，依赖 F2 修完后端到端测试）

修完后重跑：
```bash
make check
uv run pytest -q
# 前端冒烟：assignments → 开始游戏 → 事件时间线滚动 → DAY_SPEECH 提交发言 → 1s 内出现
```

全绿后提交 "fix: STEP-06 收尾 - SSE live-game + format + budget + docs + wolf-chat-guard"。
