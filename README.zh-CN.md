# 🐺 Wolven Hunt | 狼人杀 AI 竞技场

<div align="center">

**一个基于 AI 的 10 人狼人杀游戏**

[English](README.md) | 📖 **中文**

</div>

---

## 🎮 什么是 Wolven Hunt？

Wolven Hunt 是一个完全自动化的 AI 狼人杀游戏，10 个 AI 智能体在经典的狼人杀设定中竞技。通过实时网页界面观看 AI 玩家辩论、欺骗和推理，直到最终胜利。

**核心特性：**
- 🎭 **经典 10 人局**：3 狼人、4 村民、1 预言家、1 女巫、1 守卫
- 🤖 **多模型支持**：通过 LiteLLM 为每个座位路由不同的大语言模型
- 📺 **实时观战视图**：SSE 流式传输、音效提示、最终身份揭示
- 🎯 **确定性引擎**：基于 Python 的游戏逻辑，仅追加事件日志
- 🔄 **回放与重模拟**：回顾已完成的游戏或从任意状态重新模拟
- ⚡ **内置 API 密钥**：使用作者提供的轮换密钥立即开始游戏

## 🚀 快速开始（3 条命令）

```bash
# 1. 安装依赖
npm install && uv sync --extra dev

# 2. 构建前端并启动服务器
make serve-prod

# 3. 打开浏览器
open http://localhost:7002
```

就这么简单！游戏包含预配置的 API 密钥，你可以立即开始真实的 AI 对局。

## 📋 环境要求

- **Python 3.11+**（已在 3.11-3.13 测试）
- **Node.js 20+**（用于前端）
- **uv**（Python 包管理器） - 安装：`curl -LsSf https://astral.sh/uv/install.sh | sh`

## 🎯 使用方法

### 生产模式（首次推荐）
```bash
make serve-prod
```
- 构建优化后的前端
- 从 7002 端口提供所有服务
- 打开 http://localhost:7002

### 开发模式（热重载）
```bash
make dev
```
- 前端开发服务器在 7001 端口，支持热重载
- 后端 API 在 7002 端口
- Vite 自动代理 API 请求

### 无头模拟（无 UI）
```bash
make simulate
```
使用确定性种子运行完整游戏，并将结果保存到 `runs/` 目录。

## 🔧 配置

### 使用内置密钥
项目在 `.env` 中包含开箱即用的轮换 API 密钥。这些密钥是公开共享的，有速率限制 - 非常适合试玩。

### 使用你自己的密钥
长期稳定使用：

1. **方法 A：浏览器设置**（推荐）
   - 在 http://localhost:7002 打开游戏
   - 点击 **Settings** → **Model Configs**
   - 输入你的 `apiKey`、`baseUrl` 和 `modelName`
   - 设置保存在浏览器 localStorage 中

2. **方法 B：环境变量**
   编辑 `.env` 文件：
   ```bash
   WH_LLM_PROVIDER=litellm
   WH_LLM_API_KEY=你的密钥
   WH_LLM_BASE_URL=https://api.openai.com/v1
   WH_LLM_MODEL=gpt-4-turbo
   ```

### 关键环境变量
- `WH_LLM_PROVIDER`：LLM 提供商类型（`mock`、`litellm` 等）
- `WH_LLM_API_KEY`：你的 API 密钥
- `WH_LLM_MODEL`：模型名称（例如 `gpt-4-turbo`、`claude-3-5-sonnet`）
- `WH_PACING_PROFILE`：游戏速度（`instant`、`fast`、`live`、`cinematic`）

查看 `.env.example` 了解所有可用选项。

## 🧪 测试

```bash
# 运行所有测试
make test

# 快速测试（跳过慢速测试）
make test-fast

# 前端测试
npm run test:frontend

# 类型检查
make typecheck

# 代码检查
make lint
```

## 📁 项目结构

```
Wolven Hunt/
├── src/
│   ├── wolven_hunt/          # Python 后端
│   │   ├── agents/           # AI 智能体逻辑
│   │   ├── api/              # FastAPI 服务器
│   │   ├── core/             # 游戏引擎
│   │   └── llm/              # LLM 集成
│   ├── components/           # React 组件
│   ├── hooks/                # React 钩子
│   └── lib/                  # 前端工具
├── configs/                  # 游戏配置文件
├── runs/                     # 游戏历史和日志
├── tests/                    # Python 测试套件
└── public/                   # 静态资源
```

## 🛠️ 开发

### 后端开发
```bash
# 启动 API 服务器（自动重载）
uv run python -m wolven_hunt.cli serve --host 127.0.0.1 --port 7002
```

### 前端开发
```bash
# 启动 Vite 开发服务器
npm run dev
```

### 同时运行（推荐）
```bash
make dev
```

## 🐛 故障排除

### 端口被占用
```bash
# 杀掉 7002 端口的进程
lsof -ti:7002 | xargs kill -9

# 或使用不同端口
WH_API_PORT=8000 make serve-prod
```

### Python 依赖问题
```bash
# 清理并重新安装
rm -rf .venv
uv sync --extra dev
```

### 前端构建失败
```bash
# 清理并重新构建
rm -rf node_modules dist
npm install
npm run build
```

### 游戏无法启动
- 检查浏览器控制台错误（F12）
- 验证 API 是否运行：`curl http://localhost:7002/healthz`
- 检查 `.env` 文件配置是否有效

## 📚 了解更多

- **架构**：查看 `architecture.md` 了解系统设计
- **智能体逻辑**：查看 `AGENTS.md` 了解 AI 行为细节
- **API 文档**：服务器运行时访问 `http://localhost:7002/docs`

## 🤝 贡献

这是一个研究项目，欢迎 fork 和实验！

## 📄 许可证

专有 - 查看项目了解详情

---

<div align="center">

**Made with ❤️ for AI Gaming Research**

</div>
