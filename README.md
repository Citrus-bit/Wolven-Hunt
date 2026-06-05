# Wolven Hunt | 狼人杀 AI 竞技场

<div align="center">

**打开网页，就能看 10 个 AI 玩一局完整狼人杀。**

[English](README.en.md) | 中文

</div>

---

## 这是什么？

Wolven Hunt 是一个可以本地运行的 AI 狼人杀项目。你启动服务器后，在浏览器里点击开始游戏，就能观看 10 个 AI 玩家按狼人杀规则发言、投票、夜晚行动，直到游戏结束并公开全部身份。

默认板子是固定 10 人局：

- 3 个狼人
- 4 个村民
- 1 个预言家
- 1 个女巫
- 1 个守卫

项目适合两类人：

- **只想体验的人**：按快速开始启动，打开网页观看 AI 对局。
- **想开发或研究的人**：查看事件日志、回放、模型配置、复盘报告和后端 API。

## 现在支持什么？

- **实时观赛**：网页通过 SSE 接收游戏事件，支持音效、夜晚特效、倒计时和投票直方图。
- **多模型座位**：每个座位可以配置不同的 LLM provider / model，通过 LiteLLM 调用。
- **内置公开轮换密钥**：项目 `.env` 中包含可直接试玩的公开共享密钥，有速率限制；长期使用建议换成你自己的 key。
- **单真人玩家模式**：可以让 1 个真人坐进某个座位，其余 9 个座位由 AI 托管。
- **历史复盘**：已完成的游戏会保存到 `runs/`，可在网页里回看。
- **终局揭示**：游戏结束后公开所有座位身份、阵营胜负和关键摘要。
- **赛后复盘报告**：可生成 spectator-safe 的赛后分析，不暴露 API key、raw response 或玩家私有视角。
- **确定性引擎**：核心游戏逻辑由 Python FSM 驱动，事件日志 append-only，是回放和测试的单一事实源。

## 快速开始

### 方法 A：一键启动

macOS / Linux:

```bash
./start.sh
```

Windows:

```cmd
start.bat
```

脚本会检查环境、安装依赖、构建前端、启动后端，并打开 `http://localhost:7002`。

### 方法 B：手动启动

```bash
# 1. 安装依赖
npm install && uv sync --extra dev

# 2. 构建前端并启动服务器
make serve-prod

# 3. 打开浏览器
open http://localhost:7002
```

如果你的系统没有 `open` 命令，直接在浏览器地址栏访问：

```text
http://localhost:7002
```

## 第一次运行会发生什么？

1. `npm install` 安装前端依赖。
2. `uv sync --extra dev` 创建 Python 虚拟环境并安装后端依赖。
3. `make serve-prod` 先构建前端，再启动 FastAPI 服务器。
4. 浏览器打开 `http://localhost:7002`。
5. 在大厅点击开始游戏，选择 AI 观赛局或真人单座模式。
6. 游戏过程和结果会保存到 `runs/{game_id}/`。

首次安装会慢一些；之后再次启动通常只需要运行 `make serve-prod` 或 `./start.sh`。

## 环境要求

- Python 3.11+，已在 3.11 到 3.13 测试
- Node.js 20+
- uv，Python 包管理器

安装 uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows 用户也可以用：

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

## 常用操作

### 看一局 AI 对局

1. 启动项目并打开 `http://localhost:7002`。
2. 点击开始游戏。
3. 使用默认模型配置，或在开始前给不同座位分配模型。
4. 进入游戏现场后观看 AI 自动发言、行动和投票。

### 让真人加入一局

1. 在开始游戏弹窗中选择真人座位，或选择随机座位。
2. 可选择真人角色：村民、狼人、预言家、女巫、守卫或随机。
3. 游戏轮到真人时，网页会显示可选目标或文本输入。
4. 真人只能看到自己座位该看到的信息；私有视角仍由后端 Referee 过滤。

### 配置模型

浏览器方式：

1. 打开 `http://localhost:7002`。
2. 点击 Settings。
3. 进入 Model Configs。
4. 填入 `apiKey`、`baseUrl`、`modelName`。
5. 配置会保存到浏览器 localStorage。

环境变量方式，编辑 `.env`：

```bash
WH_LLM_PROVIDER=litellm
WH_LLM_API_KEY=你的密钥
WH_LLM_BASE_URL=https://api.openai.com/v1
WH_LLM_MODEL=gpt-4-turbo
```

常用变量：

- `WH_LLM_PROVIDER`：`mock` 或 `litellm`
- `WH_LLM_API_KEY`：LLM API key
- `WH_LLM_BASE_URL`：兼容 OpenAI API 的服务地址
- `WH_LLM_MODEL`：模型名
- `WH_LLM_PROVIDER_MAP`：每个座位单独路由模型的配置文件路径
- `WH_PACING_PROFILE`：观赛节奏，支持 `live`、`fast`、`off`

更多配置见 `.env.example`。

### 查看历史复盘

游戏结束后，在大厅进入历史复盘即可查看已经保存的对局。后端也会从 `runs/` 读取历史记录。

### 无 UI 模拟一局

```bash
make simulate
```

这个命令使用确定性 seed 跑完整局，适合检查引擎和事件日志。

## 数据保存在哪里？

每局默认保存到：

```text
runs/{game_id}/
```

常见文件：

- `manifest.json`：本局配置、seed、开始结束时间、座位展示信息。
- `events.jsonl`：完整事件日志，是回放和胜负判定的核心来源。
- `narrative.jsonl`：给观众看的中文叙事流。
- `final_reveal.json`：终局身份揭示。
- `review_report.json`：赛后复盘报告。
- `raw_responses.jsonl`：LLM 原始响应私有文件，只用于调试和重模拟，不进入 PlayerView、spectator API、narrative 或 SSE。

## 开发模式

同时启动前端热重载和后端：

```bash
make dev
```

端口：

- 前端 Vite：`http://localhost:7001`
- 后端 API：`http://localhost:7002`

单独启动后端：

```bash
uv run python -m wolven_hunt.cli serve --host 127.0.0.1 --port 7002
```

单独启动前端：

```bash
npm run dev
```

## API 入口

服务器运行后，可以打开：

```text
http://localhost:7002/docs
```

常用接口：

- `POST /games`：创建游戏。
- `POST /games/{game_id}/run`：开始运行已创建的游戏。
- `GET /games/{game_id}/stream`：观众 SSE 事件流。
- `GET /games/{game_id}/narrative`：观众安全的叙事流。
- `GET /games/{game_id}/effects`：观赛特效投影。
- `GET /games/{game_id}/reveal`：终局身份揭示。
- `GET|POST /games/{game_id}/review-report`：读取或生成赛后复盘报告。
- `GET /games/{game_id}/seat/{seat}/stream`：真人座位私有 SSE，需要 `player_token`。
- `POST /games/{game_id}/seat/{seat}/action`：真人提交动作，需要 `player_token`。

## 测试和检查

普通体验用户不需要运行这些命令；开发或改代码时再看。

```bash
# 运行全部 Python 测试
make test

# 快速测试，跳过较慢的 golden/property 测试
make test-fast

# 前端测试
npm run test:frontend

# Python 类型检查
make typecheck

# 代码检查
make lint
```

CI 和默认测试应使用 mock provider。真实 LLM smoke test 需要显式环境变量开启，避免默认联网或消耗 API key。

## 项目结构

```text
Wolven Hunt/
├── src/
│   ├── wolven_hunt/          # Python 后端、FSM、Referee、LLM 接入
│   ├── components/           # React 组件
│   ├── hooks/                # React hooks
│   └── lib/                  # 前端工具
├── configs/                  # 游戏、模型、prompt 配置
├── tests/                    # Python 和前端测试
├── public/                   # 静态资源
├── runs/                     # 本地游戏历史，默认不提交
├── plan.md                   # 项目规则和阶段基准
└── architecture.md           # 从 plan.md 落地的架构契约
```

## 故障排除

### 端口 7002 被占用

结束占用端口的进程：

```bash
lsof -ti:7002 | xargs kill -9
```

或临时换端口启动生产服务：

```bash
npm run build
uv run python -m wolven_hunt.cli serve-prod --host 0.0.0.0 --port 8000
```

然后访问：

```text
http://localhost:8000
```

### Python 依赖异常

```bash
rm -rf .venv
uv sync --extra dev
```

### 前端构建失败

```bash
rm -rf node_modules dist
npm install
npm run build
```

### 页面打不开或游戏无法启动

```bash
curl http://localhost:7002/healthz
```

如果返回健康状态，说明后端已启动。仍有问题时，打开浏览器开发者工具查看 Console 和 Network。

## 了解更多

- 快速参考：[QUICKSTART.md](QUICKSTART.md)
- 架构说明：[architecture.md](architecture.md)
- 项目开发约束：[AGENTS.md](AGENTS.md)
- Prompt 说明：[configs/prompts/README.md](configs/prompts/README.md)

## 许可证

Proprietary。具体使用和分发边界以项目说明为准。
