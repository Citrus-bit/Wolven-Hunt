# STEP-08 改动方案：生产就绪与开源分发

## Context

Wolven Hunt 项目当前已完成 STEP-01 到 STEP-07，后端核心引擎（Referee、FSM、EventLog、LLM Gateway、SSE、pacing/ack、narrative、role_reveal）和前端观赛 UI（per-seat model swap、countdown、vote histogram、witch witch video、final reveal）均已实现。**后端已支持真实 LLM 调用**（LiteLLM 是真实实现，不是 stub），配置驱动（YAML）已落地，replay resimulate 机制已完整。

**但工程化严重不足**，阻碍了"开源分发 + 本地运行"的目标：

1. **部署痛点**：前端 5173 跨域请求后端 8000（两个端口都太常见，本机服务冲突概率高）；需要维护 CORS 白名单；没有单命令启动；后端默认绑定 127.0.0.1 无法从其他机器访问；没有部署配置文档。
2. **文档过时**：README.md 还在说 STEP-05 "intentionally does not connect real LLMs"，给人 mock-first 印象；plan.md 和 architecture.md 没有定义 STEP-08 或"开源发布"里程碑；没有部署拓扑规范；作者付费 + 玩家免费 + 每月轮换 API key 的产品定位没有写进任何文档。
3. **测试缺失**：没有 CI（.github/workflows/ 不存在）；没有真实 LLM smoke test（所有 @pytest.mark.llm 测试都用 mock）；前端只有 2 个纯函数单测，没有 E2E。
4. **前端健壮性不足**：SSE 断线不自动重连；没有网络错误 UI 反馈；pacing 模式硬编码为 `live`，无法切换。
5. **功能缺失**：前端没有 replay UI（后端已有 replay 端点）；HumanPlayer 是 stub（9 个 NotImplementedError）。

**关于硬编码 API key**（明确**不是**问题）：`src/lib/modelConfigs.ts` 的 `MODEL_CONFIG_DEFAULTS` 里明文带着 10 个 baseUrl + apiKey 是**有意为之的产品设计**——作者自费购买 API key，玩家 clone 下来开箱即玩；key 每月由作者轮换一次。`ModelConfigList` 已有 localStorage 覆盖入口，需要长期使用的玩家可以在设置里填自己的 key。STEP-08 不动这块代码，只在 README / StartModal 文案中把这条产品策略写清楚。

**STEP-08 目标**：将项目从"功能完整的原型"升级为"可开源分发的生产就绪应用"，让任何用户能够 `git clone` → `uv sync` + `npm install` → 单命令启动 → 用作者预填的 API key 立即玩真实 LLM 对局，或者在设置里替换成自己的 key 长期使用。

---

## 技术选型决策

### 端口选择
**后端（uvicorn API）：7002**  
**前端（Vite dev）：7001**

理由：5173 / 8000 / 3000 太常见，本机其他服务占用概率高。7001 / 7002 是 IANA 注册端口区的冷门段，冲突概率接近零。

### 反向代理 / 同源策略
**选择：Vite proxy (dev) + uvicorn StaticFiles (prod)**

- **Dev 模式**：`vite.config.ts` 配置 `server.proxy`，将 `/games/*` 和 `/healthz` 代理到 `http://localhost:7002`。前端 fetch 用相对路径，浏览器同源，零 CORS。
- **Prod 模式**：uvicorn 同时 serve `dist/` 静态文件和 API，单端口 7002。FastAPI 挂载 `StaticFiles` 中间件，路由优先级：`/games/*` → API，`/*` → 静态文件 fallback。
- **优势**：零外部依赖（不需要 nginx/Caddy），改动最小，用户最易跑通（一个端口、一条命令）。

### Docker 支持
**选择：不需要，走 bare scripts**

- 保持 `uv` + `npm` 的原生工作流，不引入 docker-compose。
- 理由：LLM API 调用是网络 I/O，容器化无实质好处；开源本地玩的场景下，"clone 就能跑"比"先装 docker"门槛更低。

### 时间约束
**选择：无硬截止，按工程合理节奏推进**

- STEP-08 内部分 5 批落地，每批可独立验证：
  1. **CI + 代码质量门禁**
  2. **同源部署 + 单命令启动**
  3. **真实 LLM smoke test + API key 管理**
  4. **前端健壮性（SSE 重连、错误 UI、pacing 切换）**
  5. **Replay UI + 文档完善**

---

## 改动方案（分 5 批）

### 批次 1：CI + 代码质量门禁

**目标**：建立自动化测试门禁，防止回归。

#### 1.1 GitHub Actions workflow
创建 `.github/workflows/ci.yml`：
- **Python 测试**：`uv sync --extra dev` → `pytest -ra --strict-markers` → `mypy src/`
- **前端测试**：`npm ci` → `npm run test` → `npm run build`（验证构建不报错）
- **环境**：Python 3.11, Node 20, Ubuntu latest
- **触发**：push to main, pull_request
- **默认 mock provider**：`WH_PACING_PROFILE=off`（已在 conftest.py 设置）

#### 1.2 代码清理
- 移除 `src/components/Game/StartModal.tsx:11` 的 `console.log('[lobby] enter game')`
- 移除 `src/components/Game/GamePage.tsx:548-562` 的 `[debug] 推进` 按钮（或改为仅在 `import.meta.env.DEV && import.meta.env.VITE_DEBUG_MODE` 时显示）

#### 1.3 Replay resimulate 路径修复
`src/wolven_hunt/storage/replay.py` 对旧 run 保留 `classic_8` 回退；新 run 必须通过 `manifest.json.config_path` 恢复原始配置，默认路径使用 `classic_10`。

**修复方案**：
- `replay_resimulate()` 增加参数 `config_path: Path | None = None`
- 如果 `config_path` 为 None，从 `events.jsonl` 的 `game_start` 事件中读取 `config_hash`，然后在 `runs/{game_id}/manifest.json` 中查找原始 config 路径（需要在 manifest 中新增 `config_path` 字段）
- CLI `resimulate` 子命令增加 `--config` 选项

**验证**：在 `tests/integration/test_resimulate_consistency.py` 中增加一个测试，验证 resimulate 能从 manifest 自动恢复 config。

---

### 批次 2：同源部署 + 单命令启动

**目标**：消除 CORS，实现单端口、单命令启动。

#### 2.1 Vite proxy（dev 模式）
修改 `vite.config.ts`：
```ts
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 7001,
    proxy: {
      '/games': 'http://localhost:7002',
      '/healthz': 'http://localhost:7002',
    },
  },
});
```

修改 `src/lib/gameApi.ts:54-56`：
```ts
const API_BASE =
  import.meta.env.VITE_WH_API_BASE?.replace(/\/+$/, '') ?? '';
```
（空字符串 → 相对路径 → 浏览器同源 → Vite proxy 转发）

#### 2.2 uvicorn StaticFiles（prod 模式）
在 `src/wolven_hunt/api/app.py` 中增加 prod 模式路由：
```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# 在 create_app() 末尾，CORS 中间件之后
if settings.serve_static:
    static_dir = Path(__file__).parent.parent.parent.parent / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
```

`src/wolven_hunt/config/settings.py` 修改默认端口并增加 serve_static：
```python
api_port: int = Field(default=7002, ge=1, le=65535)  # 改自 8000
serve_static: bool = Field(default=False)
```

`src/wolven_hunt/cli.py` 增加 `serve-prod` 子命令：
```python
@cli.command()
def serve_prod(host: str = "0.0.0.0", port: int = 7002):
    """Serve both API and frontend static files (production mode)."""
    os.environ["WH_SERVE_STATIC"] = "true"
    os.environ["WH_API_HOST"] = host
    os.environ["WH_API_PORT"] = str(port)
    # 移除 CORS 中间件（同源不需要）
    os.environ["WH_API_CORS_ORIGINS"] = ""
    uvicorn.run("wolven_hunt.api.app:create_app", factory=True, host=host, port=port)
```

同时把 `settings.py` 里 `api_cors_origins` 默认值从 `("http://localhost:5173",)` 改为 `("http://localhost:7001",)`，保持 dev 模式下后端 CORS 白名单与前端 dev 端口一致（虽然 Vite proxy 后已不需要，但保留作为 fallback，方便用户绕开 proxy 直接调试）。

#### 2.3 Makefile 单命令启动
```makefile
.PHONY: serve serve-prod
serve:  ## Backend only (dev mode, port 7002)
	uv run wolven-hunt serve --host 127.0.0.1 --port 7002

serve-prod:  ## Build frontend + serve everything on port 7002
	@echo "Building frontend..."
	npm run build
	@echo "Starting production server on http://0.0.0.0:7002"
	uv run wolven-hunt serve-prod
```

#### 2.4 移除 CORS 中间件（prod 模式）
在 `app.py` 中，仅当 `settings.api_cors_origins` 非空时才挂载 `CORSMiddleware`：
```python
if settings.api_cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.api_cors_origins, ...)
```

**验证**：
1. Dev: `make serve` (后端 7002) + `npm run dev` (前端 7001) → 浏览器访问 `http://localhost:7001` → 开始游戏 → 检查 Network 面板无 CORS preflight（请求走 Vite proxy）
2. Prod: `make serve-prod` → 浏览器访问 `http://localhost:7002` → 开始游戏 → 检查前端和 API 都在同一个 origin

---

### 批次 3：真实 LLM smoke test + API key 文档化

**目标**：验证真实 LLM 调用链路，在文档中明确 API key 轮换策略。

#### 3.1 真实 LLM smoke test
在 `tests/integration/` 新增 `test_real_llm_smoke.py`：
```python
import pytest
import os

@pytest.mark.skipif(
    not os.getenv("WH_REAL_LLM_SMOKE"),
    reason="Real LLM smoke test requires WH_REAL_LLM_SMOKE=1"
)
@pytest.mark.llm
def test_real_llm_single_call():
    """Smoke test: call a real LLM provider and verify structured output."""
    # 使用 WH_LLM_PROVIDER=litellm, WH_LLM_API_KEY=<real key>
    # 调用 LLMGateway.call() 一次，验证返回 JSON 符合 schema
    # 不跑完整游戏（成本高），只验证单次调用
    ...

@pytest.mark.skipif(
    not os.getenv("WH_REAL_LLM_SMOKE"),
    reason="Real LLM smoke test requires WH_REAL_LLM_SMOKE=1"
)
@pytest.mark.llm
def test_real_llm_full_game():
    """Smoke test: run a full 10-player game with real LLM (expensive)."""
    # 仅在手动触发时运行（GitHub Actions manual dispatch）
    ...
```

在 `.github/workflows/ci.yml` 中增加一个 manual dispatch job：
```yaml
  real-llm-smoke:
    runs-on: ubuntu-latest
    if: github.event_name == 'workflow_dispatch'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install uv && uv sync --extra dev
      - run: pytest -m llm
        env:
          WH_REAL_LLM_SMOKE: "1"
          WH_LLM_PROVIDER: litellm
          WH_LLM_API_KEY: ${{ secrets.WH_LLM_API_KEY }}
```

#### 3.2 API key 文案 + 兜底体验（**保留硬编码默认 key**）

`src/lib/modelConfigs.ts` 中的 10 个默认 baseUrl + apiKey 是产品设计的一部分（作者付费、玩家免费、每月轮换），**不删除**。本批次只补齐"为什么这些 key 在代码里"的说明，让首次接触项目的人不会误判为安全漏洞，同时给玩家替换成自己 key 的清晰指引。

**改动**：
1. `src/components/Lobby/modals/StartModal.tsx:19` 当前文案"所有 api key 均为作者本人自行购买，免费开放"已经在场，但信息不全。改为：
   > "作者已预填 10 个模型的 API key（自费购买），每月轮换一次。  
   > 如需长期稳定使用，请进入【设置】→【模型配置】填入你自己的 key（保存在浏览器 localStorage，优先级高于默认值）。"
2. `src/components/Lobby/modals/ModelConfigList.tsx`：在每个 slot 的 apiKey 输入框上方加一行小字提示："留空则使用作者预填的轮换 key"。
3. 在 `src/lib/modelConfigs.ts` 顶部加一段注释（对开发者，不是用户）：
   ```ts
   // NOTE: 默认 apiKey 是作者自费的轮换 key，每月更新一次。
   // 这是产品设计的一部分（开箱即玩），不是安全漏洞。
   // 用户可在 ModelConfigList UI 中覆盖为自己的 key（存 localStorage）。
   ```
4. README 的 Configuration 章节同步说明这个策略（见 5.2）。

**不做**的事：
- 不清空 `MODEL_CONFIG_DEFAULTS` 里的 apiKey 字段
- 不在 Settings UI 加红色警告图标
- 不强制用户配置自己的 key

#### 3.3 .env.example 完善
增加 `VITE_WH_API_BASE` 说明：
```bash
# Frontend API base URL (leave empty for same-origin in prod / Vite proxy in dev)
# 仅在你想绕开 Vite proxy 直接打后端时设置，例如:
# VITE_WH_API_BASE=http://localhost:7002
```

同时把 `WH_API_PORT` 默认值更新为 7002，`WH_API_CORS_ORIGINS` 默认值更新为 `http://localhost:7001`。

---

### 批次 4：前端健壮性（SSE 重连、错误 UI、pacing 切换）

**目标**：提升前端在网络不稳定、LLM 慢响应场景下的用户体验。

#### 4.1 SSE 自动重连
`src/components/Game/GamePage.tsx:150-166` 当前 SSE `onerror` 只做一次 poll，不重连。

**修复方案**：
- 增加 `reconnectAttempts` 状态（最多 5 次）
- `onerror` 时，延迟 2s → 重新调用 `subscribeGameEvents`
- 如果 5 次都失败，显示"连接失败，请刷新页面"

#### 4.2 网络错误 UI 反馈
在 `GameTopBar.tsx` 中增加一个 `<Alert>` 组件：
- `streamStatus === 'error'` 时显示："事件流断开，正在重连..."
- `reconnectAttempts >= 5` 时显示："连接失败，请检查网络或刷新页面"

#### 4.3 Pacing 模式切换 UI
`GamePage.tsx:419` 当前硬编码 `pacing: 'live'`。

**修复方案**：
- 在 `GameTopBar.tsx` 增加一个下拉菜单：`live` / `fast` / `off`
- 存储在 `localStorage` 中（key: `wolven_hunt.pacing_mode`）
- `createGame` 时读取并传入

#### 4.4 Countdown 超时状态
`GamePhaseHeader.tsx` 当前倒计时到 0 后显示 `0s`，但游戏可能还在等 LLM。

**修复方案**：
- 倒计时到 0 后，如果游戏还未进入下一阶段，显示 `"等待中..."`

---

### 批次 5：Replay UI + 文档完善

**目标**：让用户能回放历史对局，完善开源分发文档。

#### 5.1 Replay UI
在 `src/components/Lobby/modals/HistoryModal.tsx` 中实现：
- 读取 `runs/` 目录下的所有 `manifest.json`（需要后端增加 `GET /games` 端点返回游戏列表）
- 显示游戏列表：game_id, 开始时间, winner, 时长
- 点击某个游戏 → 跳转到 `GamePage`，但 `mode = 'replay'`
- Replay 模式下：
  - 不连接 SSE，而是一次性 `GET /games/{id}/events` 拉取所有事件
  - 增加播放控制条：播放/暂停、速度（1x/2x/5x）、进度条拖动
  - 事件按时间戳顺序播放，用 `setTimeout` 模拟时间流逝

**后端支持**：
- 增加 `GET /games` 端点：返回 `runs/` 下所有游戏的 manifest 列表
- 增加 `GET /games/{id}/events` 端点：返回完整 events.jsonl（已有 `GET /games/{id}/narrative`，可复用逻辑）

#### 5.2 README 重写
当前 README 只有 27 行且过时。重写为：

```markdown
# Wolven Hunt (AI 狼人杀)

10-player AI werewolf game with real-time spectating and LLM-powered agents.

## Features
- 10 roles: 3 wolves, 4 villagers, 1 seer, 1 witch, 1 guard
- Per-seat LLM provider routing (OpenAI, Anthropic, Gemini, etc.)
- Real-time spectator view with SSE
- Audio narration and witch witch video
- Deterministic replay and resimulation
- Config-driven rules, roles, and prompts

## Quick Start

### Prerequisites
- Python ≥3.11
- Node.js ≥20
- uv (Python package manager)

### Installation
\`\`\`bash
git clone https://github.com/yourusername/wolven-hunt.git
cd wolven-hunt
uv sync --extra dev
npm install
\`\`\`

### Configuration
**作者已预填 10 个模型的 API key（自费购买），每月轮换一次。**  
Clone 下来即可直接玩，无需额外配置。

如需长期稳定使用或自定义模型：
1. 进入游戏大厅 → 点击【设置】→【模型配置】
2. 填入你自己的 baseUrl / apiKey / modelName（保存在浏览器 localStorage，优先级高于默认值）

或者：
1. 复制 `.env.example` 到 `.env`
2. 填入后端全局 LLM 配置（可选，仅当你想通过后端统一管理 key 时）

### Run (Production Mode)
\`\`\`bash
make serve-prod
\`\`\`
打开 http://localhost:7002

### Run (Development Mode)
Terminal 1:
\`\`\`bash
make serve
\`\`\`
Terminal 2:
\`\`\`bash
npm run dev
\`\`\`
打开 http://localhost:7001

## Testing
\`\`\`bash
# Python tests (mock provider)
pytest

# Frontend tests
npm test

# Real LLM smoke test (requires API key)
WH_REAL_LLM_SMOKE=1 WH_LLM_PROVIDER=litellm WH_LLM_API_KEY=<key> pytest -m llm
\`\`\`

## Project Status
- ✅ STEP-01 to STEP-07: Core engine, spectator MVP, frontend UI
- 🚧 STEP-08: Production readiness, CI, deployment, replay UI

## License
MIT
```

#### 5.3 部署指南
在 `docs/` 新增 `DEPLOYMENT.md`：
- 单机部署（make serve-prod，端口 7002）
- 多机部署（nginx 反向代理，可选）
- API key 轮换流程（作者每月更新 `src/lib/modelConfigs.ts` 中的默认 key 并 push 新 commit；用户 `git pull` 即可获取新 key）
- 环境变量完整列表（包括端口 7002 / 7001 的说明）

#### 5.4 plan.md 和 architecture.md 更新
- 在 `plan.md` 末尾增加 STEP-08 章节（本文档内容）
- 在 `architecture.md` 增加"部署拓扑"章节（Vite proxy + uvicorn StaticFiles）
- 更新 `plan.md:463` 的措辞：从"缺省为 mock"改为"生产使用 litellm，CI 使用 mock 以节省成本"

---

## 验证清单

### 批次 1 验证
- [ ] GitHub Actions CI 通过（Python tests + mypy + frontend build）
- [ ] `pytest -ra` 无失败
- [ ] `npm run build` 无报错
- [ ] Replay resimulate 能从 manifest 自动恢复 config

### 批次 2 验证
- [ ] Dev 模式：`make serve` (后端 7002) + `npm run dev` (前端 7001) → 浏览器 Network 面板无 CORS preflight
- [ ] Prod 模式：`make serve-prod` → 单端口 7002 同时 serve 前端和 API
- [ ] Prod 模式：前端 fetch 用相对路径，无 CORS 错误

### 批次 3 验证
- [ ] `WH_REAL_LLM_SMOKE=1` 下 smoke test 通过（需手动触发，消耗 API quota）
- [ ] StartModal 文案准确说明"作者预填 key + 每月轮换 + 可在设置里替换"
- [ ] ModelConfigList 每个 slot 有"留空则使用作者预填的轮换 key"提示

### 批次 4 验证
- [ ] SSE 断线后自动重连（最多 5 次）
- [ ] 重连失败后显示错误提示
- [ ] Pacing 模式可在 UI 切换（live/fast/off）
- [ ] Countdown 到 0 后显示"等待中..."

### 批次 5 验证
- [ ] 历史对局列表显示正确
- [ ] 点击某个对局进入 replay 模式
- [ ] Replay 播放控制条正常（播放/暂停/速度/进度条）
- [ ] README 准确反映当前状态
- [ ] `make serve-prod` 一条命令启动成功

---

## 关键文件清单

### 需要修改的文件
- `vite.config.ts` - 增加 server.port: 7001 + server.proxy
- `src/lib/gameApi.ts` - API_BASE 改为空字符串
- `src/lib/modelConfigs.ts` - 顶部增加注释说明默认 key 策略
- `src/components/Lobby/modals/StartModal.tsx` - 更新 API key 说明文案
- `src/components/Lobby/modals/ModelConfigList.tsx` - 每个 slot 增加"留空则使用作者预填的轮换 key"提示
- `src/wolven_hunt/api/app.py` - 增加 StaticFiles 挂载
- `src/wolven_hunt/config/settings.py` - api_port 改为 7002, api_cors_origins 改为 http://localhost:7001, 增加 serve_static 字段
- `src/wolven_hunt/cli.py` - 增加 serve-prod 子命令
- `src/wolven_hunt/storage/replay.py` - 修复 resimulate 路径硬编码
- `src/components/Game/GamePage.tsx` - SSE 重连、pacing 切换
- `src/components/Game/GameTopBar.tsx` - 错误 UI、pacing 下拉菜单
- `src/components/Game/GamePhaseHeader.tsx` - Countdown 超时状态
- `src/components/Lobby/modals/HistoryModal.tsx` - Replay UI
- `Makefile` - 更新 serve target 端口为 7002, 增加 serve-prod target
- `README.md` - 完全重写
- `plan.md` - 增加 STEP-08 章节
- `architecture.md` - 增加部署拓扑章节
- `.env.example` - 更新端口默认值，增加 VITE_WH_API_BASE 说明

### 需要新增的文件
- `.github/workflows/ci.yml` - CI 配置
- `tests/integration/test_real_llm_smoke.py` - 真实 LLM smoke test
- `docs/DEPLOYMENT.md` - 部署指南

### 需要删除的内容
- `src/components/Game/StartModal.tsx:11` - console.log
- `src/components/Game/GamePage.tsx:548-562` - debug 按钮（或门控）

---

## 风险与缓解

### 风险 1：uvicorn StaticFiles 路由优先级
**风险**：如果 `/games` 路径下有静态文件（如 `dist/games/foo.js`），可能被 API 路由拦截。

**缓解**：
- FastAPI 路由优先级：精确匹配 > 前缀匹配 > 通配符。`/games/{id}` 是精确匹配，`/` 是通配符，不会冲突。
- 验证：在 `dist/games/` 下放一个 `test.txt`，访问 `/games/test.txt`，应返回 404（被 API 拦截），这是预期行为。前端不应在 `/games/` 下放静态文件。

### 风险 2：SSE 重连风暴
**风险**：如果后端崩溃，所有客户端同时重连，可能造成雪崩。

**缓解**：
- 重连延迟加入 jitter：`2s + random(0, 1s)`
- 最多 5 次重连后放弃

### 风险 3：真实 LLM smoke test 成本
**风险**：每次 CI 运行都调用真实 LLM，成本高。

**缓解**：
- 默认 CI 不运行真实 LLM 测试
- 仅在 manual dispatch 或 weekly schedule 时运行
- 单次调用测试（不跑完整游戏）成本 < $0.01

### 风险 4：Replay UI 性能
**风险**：完整事件日志可能有数百条事件，一次性加载可能卡顿。

**缓解**：
- 后端 `GET /games/{id}/events` 支持分页（`?offset=&limit=`）
- 前端按需加载（初始加载前 100 条，滚动时加载更多）

---

## 后续工作（STEP-09 候选）

以下工作不在 STEP-08 范围内，可延后到 STEP-09：

1. **HumanPlayer 实现**：允许真人玩家入座，per-seat SSE 推送私有信息
2. **Property test 扩展**：Hypothesis 覆盖更多 invariants
3. **千局公平性回归**：统计各角色胜率，验证平衡性
4. **Token 预算实测**：真实 LLM 下的 token 消耗分布
5. **Prompt A/B 测试**：不同 prompt 版本的胜率对比
6. **多语言支持**：英文 prompt pack
7. **Docker Compose 可选支持**：为愿意用 docker 的用户提供备选
8. **HTTPS / LAN 多人观赛**：Caddy 自动 HTTPS，局域网多设备观赛

---

## 交付给 GPT 的执行指令

请按以下顺序执行 STEP-08 的 5 个批次：

1. **批次 1（CI + 代码质量）**：创建 `.github/workflows/ci.yml`，修复 replay resimulate 路径硬编码，移除 debug 代码。验证 CI 通过。
2. **批次 2（同源部署）**：修改 `vite.config.ts`、`gameApi.ts`、`app.py`、`settings.py`、`cli.py`、`Makefile`。验证 dev 和 prod 模式都无 CORS 错误。
3. **批次 3（真实 LLM smoke + API key 文档化）**：创建 `test_real_llm_smoke.py`，更新 StartModal / ModelConfigList 的 API key 说明文案，在 modelConfigs.ts 顶部加注释说明默认 key 是设计意图，更新 `.env.example`（端口默认值改为 7002 / 7001，增加 VITE_WH_API_BASE 说明）。**保留**所有硬编码默认 key。手动验证 smoke test（需 API key）。
4. **批次 4（前端健壮性）**：修改 `GamePage.tsx`、`GameTopBar.tsx`、`GamePhaseHeader.tsx`，增加 SSE 重连、错误 UI、pacing 切换。验证网络断线场景。
5. **批次 5（Replay UI + 文档）**：实现 `HistoryModal.tsx` replay 功能，增加后端 `GET /games` 和 `GET /games/{id}/events` 端点，重写 `README.md`，创建 `docs/DEPLOYMENT.md`，更新 `plan.md` 和 `architecture.md`。验证完整 replay 流程。

每个批次完成后，运行对应的验证清单，确保无回归。所有批次完成后，项目即达到"开源分发就绪"状态。
