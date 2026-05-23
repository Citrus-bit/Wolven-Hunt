# Wolven Hunt

Wolven Hunt is a 10-player AI werewolf game with a deterministic Python engine, FastAPI spectator API, and React frontend.

## Features

- Classic 10-seat board: 3 wolves, 4 villagers, 1 seer, 1 witch, 1 guard
- Per-seat LLM provider routing through LiteLLM
- Real-time spectator view with SSE, pacing/ack, audio cues, and final role reveal
- Append-only EventLog as the source of truth for views, replay, and tests
- Deterministic replay/resimulation from `runs/{game_id}/`
- History replay UI for completed local games

## Quick Start

Prerequisites:

- Python 3.11+
- Node.js 20+
- uv

Install:

```bash
uv sync --extra dev
npm install
```

Production-style local run:

```bash
make serve-prod
```

Open [http://localhost:7002](http://localhost:7002).

Development run:

```bash
make serve
npm run dev
```

Open [http://localhost:7001](http://localhost:7001). Vite proxies `/games`, `/models`, and `/healthz` to the backend on port 7002.

## Model Keys

The frontend includes 10 author-funded rotating model keys so a fresh clone can start a real AI game. These are intentionally part of the product experience, not a security boundary.

For stable long-term use, open Settings -> Model Configs and enter your own `baseUrl`, `apiKey`, and `modelName`. Browser localStorage overrides the defaults.

## Testing

```bash
uv run pytest -ra --strict-markers
npm run test:frontend
npm run build
```

Real LLM smoke tests are opt-in:

```bash
WH_REAL_LLM_SMOKE=1 \
WH_LLM_PROVIDER=litellm \
WH_LLM_API_KEY=<key> \
WH_LLM_MODEL=<model> \
uv run pytest -m llm tests/integration/test_real_llm_smoke.py
```

Default CI uses mock providers and does not spend API quota.

## Project Status

STEP-08 focuses on local production readiness: same-origin deployment, one-command startup, non-blocking game start, SSE reconnect, history replay, CI, and current documentation.
