# 🐺 Wolven Hunt

<div align="center">

**A 10-player AI Werewolf Game**

📖 **English** | [中文](README.md)

</div>

---

## 🎮 What is Wolven Hunt?

Wolven Hunt is a fully automated AI werewolf game where 10 AI agents compete in a classic werewolf setup. Watch AI players debate, deceive, and deduce their way to victory through a real-time web interface.

**Key Features:**
- 🎭 **Classic 10-seat board**: 3 Werewolves, 4 Villagers, 1 Seer, 1 Witch, 1 Guard
- 🤖 **Multi-LLM support**: Route each seat to different LLM providers via LiteLLM
- 📺 **Real-time spectator view**: Watch games unfold with SSE streaming, audio cues, and final role reveal
- 🎯 **Deterministic engine**: Python-based game logic with append-only event log
- 🔄 **Replay & Resimulation**: Review completed games or resimulate from any state
- ⚡ **Built-in API keys**: Start playing immediately with rotating author-funded keys

## 🚀 Quick Start (3 Commands)

```bash
# 1. Install dependencies
npm install && uv sync --extra dev

# 2. Build frontend and start server
make serve-prod

# 3. Open your browser
open http://localhost:7002
```

That's it! The game includes pre-configured API keys, so you can start a real AI game immediately.

## 📋 Prerequisites

- **Python 3.11+** (tested with 3.11-3.13)
- **Node.js 20+** (for frontend)
- **uv** (Python package manager) - Install: `curl -LsSf https://astral.sh/uv/install.sh | sh`

## 🎯 Usage

### Production Mode (Recommended for first try)
```bash
make serve-prod
```
- Builds optimized frontend
- Serves everything from port 7002
- Open http://localhost:7002

### Development Mode (Hot reload)
```bash
make dev
```
- Frontend dev server on port 7001 with hot reload
- Backend API on port 7002
- Vite proxies API requests automatically

### Headless Simulation (No UI)
```bash
make simulate
```
Runs a complete game with deterministic seed and saves results to `runs/` directory.

## 🔧 Configuration

### Using Built-in Keys
The project includes rotating API keys in `.env` that work out of the box. These are publicly shared and rate-limited - perfect for trying the game.

### Using Your Own Keys
For stable long-term use:

1. **Option A: Browser Settings** (Recommended)
   - Open the game at http://localhost:7002
   - Click **Settings** → **Model Configs**
   - Enter your `apiKey`, `baseUrl`, and `modelName`
   - Settings persist in browser localStorage

2. **Option B: Environment Variables**
   Edit `.env` file:
   ```bash
   WH_LLM_PROVIDER=litellm
   WH_LLM_API_KEY=your-key-here
   WH_LLM_BASE_URL=https://api.openai.com/v1
   WH_LLM_MODEL=gpt-4-turbo
   ```

### Key Environment Variables
- `WH_LLM_PROVIDER`: LLM provider type (`mock`, `litellm`, etc.)
- `WH_LLM_API_KEY`: Your API key
- `WH_LLM_MODEL`: Model name (e.g., `gpt-4-turbo`, `claude-3-5-sonnet`)
- `WH_PACING_PROFILE`: Game speed (`instant`, `fast`, `live`, `cinematic`)

See `.env.example` for all available options.

## 🧪 Testing

```bash
# Run all tests
make test

# Quick tests (skip slow ones)
make test-fast

# Frontend tests
npm run test:frontend

# Type checking
make typecheck

# Linting
make lint
```

## 📁 Project Structure

```
Wolven Hunt/
├── src/
│   ├── wolven_hunt/          # Python backend
│   │   ├── agents/           # AI agent logic
│   │   ├── api/              # FastAPI server
│   │   ├── core/             # Game engine
│   │   └── llm/              # LLM integration
│   ├── components/           # React components
│   ├── hooks/                # React hooks
│   └── lib/                  # Frontend utilities
├── configs/                  # Game configuration files
├── runs/                     # Game history and logs
├── tests/                    # Python test suite
└── public/                   # Static assets
```

## 🛠️ Development

### Backend Development
```bash
# Start API server with auto-reload
uv run python -m wolven_hunt.cli serve --host 127.0.0.1 --port 7002
```

### Frontend Development
```bash
# Start Vite dev server
npm run dev
```

### Run Both (Recommended)
```bash
make dev
```

## 🐛 Troubleshooting

### Port Already in Use
```bash
# Kill process on port 7002
lsof -ti:7002 | xargs kill -9

# Or use different ports
WH_API_PORT=8000 make serve-prod
```

### Python Dependencies Issue
```bash
# Clean and reinstall
rm -rf .venv
uv sync --extra dev
```

### Frontend Build Fails
```bash
# Clean and rebuild
rm -rf node_modules dist
npm install
npm run build
```

### Game Won't Start
- Check browser console for errors (F12)
- Verify API is running: `curl http://localhost:7002/healthz`
- Check `.env` file has valid configuration

## 📚 Learn More

- **Architecture**: See `architecture.md` for system design
- **Agent Logic**: See `AGENTS.md` for AI behavior details
- **API Docs**: Visit `http://localhost:7002/docs` when server is running

## 🤝 Contributing

This is a research project. Feel free to fork and experiment!

## 📄 License

Proprietary - See project for details

---

<div align="center">

**Made with ❤️ for AI Gaming Research**

</div>
