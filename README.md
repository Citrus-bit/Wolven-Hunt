# Wolven Hunt

Wolven Hunt is a deterministic 8-player AI werewolf engine and React shell.

## Python Engine

Install dependencies:

```bash
uv sync --extra dev
```

Run the verification suite:

```bash
make lint
make typecheck
make test
```

Run a deterministic mock simulation:

```bash
make simulate
```

The STEP-05 backend intentionally does not connect real LLMs, FastAPI, SSE, or default disk persistence. Those pieces are reserved for later stages.
