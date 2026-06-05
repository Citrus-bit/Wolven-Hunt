# Wolven Hunt

<div align="center">

**Open the web app and watch 10 AI players run a full Werewolf game.**

English | [中文](README.md)

</div>

---

## What Is This?

Wolven Hunt is a local AI Werewolf project. Start the server, open the browser, click Start Game, and watch 10 AI players speak, vote, act at night, and play until the final role reveal.

The default board is a fixed 10-seat setup:

- 3 Werewolves
- 4 Villagers
- 1 Seer
- 1 Witch
- 1 Guard

It is useful for two groups:

- **Players and viewers**: start the app and watch an AI game from the browser.
- **Developers and researchers**: inspect event logs, replays, model routing, post-game reports, and the backend API.

## What It Supports Now

- **Live spectator mode**: SSE event streaming, audio cues, night effects, countdowns, and vote histograms.
- **Per-seat model routing**: each seat can use a different LLM provider / model through LiteLLM.
- **Built-in public rotating keys**: the committed `.env` includes shared keys for quick trials. They are rate-limited; use your own keys for stable long-term use.
- **Single human player mode**: one human can take a seat while the other 9 seats are AI-controlled.
- **History replay**: finished games are saved under `runs/` and can be reviewed later.
- **Final reveal**: the end state shows every seat's role, the winning side, and highlights.
- **Post-game review report**: spectator-safe analysis without exposing API keys, raw responses, or private player views.
- **Deterministic engine**: Python FSM game logic with an append-only event log as the source of truth for replay and tests.

## Quick Start

### Option A: One-Command Start

macOS / Linux:

```bash
./start.sh
```

Windows:

```cmd
start.bat
```

The script checks prerequisites, installs dependencies, builds the frontend, starts the backend, and opens `http://localhost:7002`.

### Option B: Manual Start

```bash
# 1. Install dependencies
npm install && uv sync --extra dev

# 2. Build the frontend and start the server
make serve-prod

# 3. Open the browser
open http://localhost:7002
```

If your system does not have the `open` command, visit this URL directly:

```text
http://localhost:7002
```

## What Happens On First Run?

1. `npm install` installs frontend dependencies.
2. `uv sync --extra dev` creates the Python environment and installs backend dependencies.
3. `make serve-prod` builds the frontend and starts the FastAPI server.
4. The browser opens `http://localhost:7002`.
5. In the lobby, start an AI spectator game or choose a single human seat.
6. Game data is saved to `runs/{game_id}/`.

The first install can take a while. After that, you usually only need `make serve-prod` or `./start.sh`.

## Requirements

- Python 3.11+, tested with 3.11 through 3.13
- Node.js 20+
- uv, the Python package manager

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows:

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

## Common Tasks

### Watch An AI Game

1. Start the project and open `http://localhost:7002`.
2. Click Start Game.
3. Use the default model setup, or assign models to seats before starting.
4. Enter the game view and watch the AI players speak, act, and vote.

### Join As One Human Player

1. In the Start Game dialog, choose a human seat or use a random seat.
2. Choose a human role: Villager, Werewolf, Seer, Witch, Guard, or Random.
3. When it is your turn, the UI shows the valid targets or text input.
4. You only see what your seat is allowed to see. Private views are filtered by the backend Referee.

### Configure Models

Browser setup:

1. Open `http://localhost:7002`.
2. Click Settings.
3. Open Model Configs.
4. Enter `apiKey`, `baseUrl`, and `modelName`.
5. The settings are stored in browser localStorage.

Environment setup, by editing `.env`:

```bash
WH_LLM_PROVIDER=litellm
WH_LLM_API_KEY=your-key-here
WH_LLM_BASE_URL=https://api.openai.com/v1
WH_LLM_MODEL=gpt-4-turbo
```

Useful variables:

- `WH_LLM_PROVIDER`: `mock` or `litellm`
- `WH_LLM_API_KEY`: LLM API key
- `WH_LLM_BASE_URL`: OpenAI-compatible API base URL
- `WH_LLM_MODEL`: model name
- `WH_LLM_PROVIDER_MAP`: path to a per-seat model routing file
- `WH_PACING_PROFILE`: spectator pacing, one of `live`, `fast`, `off`

See `.env.example` for more settings.

### Review Past Games

After a game finishes, open History Replay from the lobby. The backend reads saved games from `runs/`.

### Run A Headless Simulation

```bash
make simulate
```

This runs a full game with a deterministic seed. It is useful for checking the engine and event log.

## Where Data Is Saved

Each game is saved under:

```text
runs/{game_id}/
```

Common files:

- `manifest.json`: game config, seed, start/end time, and seat presentation metadata.
- `events.jsonl`: the full event log and core source for replay and win checks.
- `narrative.jsonl`: spectator-facing narrative rows.
- `final_reveal.json`: final role reveal.
- `review_report.json`: post-game review report.
- `raw_responses.jsonl`: private LLM raw responses for debugging and resimulation only. They do not enter PlayerView, spectator API, narrative, or SSE.

## Development Mode

Run frontend hot reload and the backend together:

```bash
make dev
```

Ports:

- Vite frontend: `http://localhost:7001`
- Backend API: `http://localhost:7002`

Start only the backend:

```bash
uv run python -m wolven_hunt.cli serve --host 127.0.0.1 --port 7002
```

Start only the frontend:

```bash
npm run dev
```

## API Entry Points

When the server is running, open:

```text
http://localhost:7002/docs
```

Useful endpoints:

- `POST /games`: create a game.
- `POST /games/{game_id}/run`: run a created game.
- `GET /games/{game_id}/stream`: spectator SSE stream.
- `GET /games/{game_id}/narrative`: spectator-safe narrative rows.
- `GET /games/{game_id}/effects`: spectator effect projections.
- `GET /games/{game_id}/reveal`: final role reveal.
- `GET|POST /games/{game_id}/review-report`: read or generate the post-game review report.
- `GET /games/{game_id}/seat/{seat}/stream`: private human-seat SSE, requires `player_token`.
- `POST /games/{game_id}/seat/{seat}/action`: submit a human-seat action, requires `player_token`.

## Tests And Checks

Regular users do not need these commands. Use them when developing or changing code.

```bash
# Run all Python tests
make test

# Quick tests, skipping slower golden/property tests
make test-fast

# Frontend tests
npm run test:frontend

# Python type checking
make typecheck

# Linting
make lint
```

CI and default tests should use the mock provider. Real LLM smoke tests must be explicitly enabled by environment variables so they do not network or spend API keys by default.

## Project Structure

```text
Wolven Hunt/
├── src/
│   ├── wolven_hunt/          # Python backend, FSM, Referee, LLM integration
│   ├── components/           # React components
│   ├── hooks/                # React hooks
│   └── lib/                  # Frontend utilities
├── configs/                  # Game, model, and prompt configs
├── tests/                    # Python and frontend tests
├── public/                   # Static assets
├── runs/                     # Local game history, not committed by default
├── plan.md                   # Project rules and stage baseline
└── architecture.md           # Architecture contract derived from plan.md
```

## Troubleshooting

### Port 7002 Is Already In Use

Stop the process using the port:

```bash
lsof -ti:7002 | xargs kill -9
```

Or temporarily start production mode on another port:

```bash
npm run build
uv run python -m wolven_hunt.cli serve-prod --host 0.0.0.0 --port 8000
```

Then visit:

```text
http://localhost:8000
```

### Python Dependency Problems

```bash
rm -rf .venv
uv sync --extra dev
```

### Frontend Build Fails

```bash
rm -rf node_modules dist
npm install
npm run build
```

### Page Does Not Open Or Game Does Not Start

```bash
curl http://localhost:7002/healthz
```

If the health endpoint responds, the backend is running. If the page still fails, check the browser DevTools Console and Network tabs.

## Learn More

- Quick reference: [QUICKSTART.md](QUICKSTART.md)
- Architecture: [architecture.md](architecture.md)
- Project development constraints: [AGENTS.md](AGENTS.md)
- Prompt notes: [configs/prompts/README.md](configs/prompts/README.md)

## License

Proprietary. Usage and redistribution boundaries follow the project documentation.
