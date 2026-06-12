# Deployment

## Local Production Mode

```bash
uv sync --extra dev
npm install
make serve-prod
```

This builds `dist/` and starts FastAPI on `0.0.0.0:7002`. API routes and frontend files are served from the same origin.

## Development Mode

Terminal 1:

```bash
make serve
```

Terminal 2:

```bash
npm run dev
```

Open `http://localhost:7001`. Vite proxies `/games`, `/models`, and `/healthz` to `http://localhost:7002`.

## Environment

- `WH_API_HOST`: default `127.0.0.1`
- `WH_API_PORT`: default `7002`
- `WH_API_CORS_ORIGINS`: default `http://localhost:7001`
- `WH_SERVE_STATIC`: set by `serve-prod`
- `WH_RUNS_DIR`: default `runs`
- `WH_PACING_PROFILE`: `live`, `fast`, or `off`
- `VITE_WH_API_BASE`: leave empty for same-origin mode; set only to bypass the proxy

## API Keys

API keys are intentionally not committed. Users can enter them in Settings -> Model Configs; localStorage values take precedence. For shared demo credentials, contact the developer for the corresponding agent keys.

Do not write API keys into frontend defaults, backend manifests, EventLog, raw responses exposed to clients, README, or deployment docs.

## LAN Access

Use production mode and open `http://<host-ip>:7002` from another device on the same network. If exposing outside a trusted LAN, put the app behind HTTPS and rotate any shared model keys promptly.
