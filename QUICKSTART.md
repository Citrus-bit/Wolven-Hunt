# 🐺 Wolven Hunt - Quick Reference | 快速参考

## One-Command Start | 一键启动

### macOS / Linux
```bash
./start.sh
```

### Windows
```cmd
start.bat
```

### Manual Start | 手动启动
```bash
npm install && uv sync --extra dev
make serve-prod
```

Then open | 然后打开: http://localhost:7002

---

## Common Commands | 常用命令

### Production Mode | 生产模式
```bash
make serve-prod       # Build and serve (recommended for first time)
```

### Development Mode | 开发模式
```bash
make dev             # Hot reload for both frontend and backend
```

### Testing | 测试
```bash
make test            # Run all tests
make test-fast       # Quick tests only
npm run test:frontend # Frontend tests
```

### Code Quality | 代码质量
```bash
make lint            # Check code style
make format          # Auto-format code
make typecheck       # Type checking
```

---

## Environment Variables | 环境变量

The project includes working API keys in `.env` for immediate use.

To use your own keys, edit `.env`:

```bash
# LLM Configuration
WH_LLM_PROVIDER=litellm
WH_LLM_API_KEY=your-key-here
WH_LLM_BASE_URL=https://api.openai.com/v1
WH_LLM_MODEL=gpt-4-turbo

# Game Pacing
WH_PACING_PROFILE=live    # instant | fast | live | cinematic
```

Or configure via browser Settings after starting the game.

---

## Troubleshooting | 故障排除

### Port 7002 already in use | 端口被占用
```bash
lsof -ti:7002 | xargs kill -9
```

### Clean install | 重新安装
```bash
rm -rf node_modules .venv dist
npm install && uv sync --extra dev
```

### Check server health | 检查服务器健康
```bash
curl http://localhost:7002/healthz
```

---

## Project Structure | 项目结构

```
├── src/wolven_hunt/     # Python backend (游戏引擎)
├── src/components/      # React frontend (界面组件)
├── configs/             # Game configs (游戏配置)
├── tests/               # Test suite (测试)
└── runs/                # Game history (游戏记录)
```

---

## API Documentation | API 文档

When server is running, visit:
http://localhost:7002/docs

---

## Support | 支持

- Full README: [README.md](README.md)
- Architecture: [architecture.md](architecture.md)
- Agent Design: [AGENTS.md](AGENTS.md)

---

**Made with ❤️ for AI Gaming Research**
