.PHONY: install lint format typecheck test test-fast test-llm check cov simulate serve serve-prod resimulate

install:
	uv sync --extra dev

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

typecheck:
	uv run mypy src/wolven_hunt

test:
	uv run pytest

test-fast:
	uv run pytest -m "not golden and not property"

test-llm:
	uv run pytest -m llm tests/unit/test_llm_schemas.py tests/unit/test_llm_gateway_retry.py tests/unit/test_cost_tracker.py tests/integration/test_llm_agent_full_loop.py

check: lint typecheck test

cov:
	uv run pytest --cov=wolven_hunt --cov-report=term-missing

simulate:
	uv run python -m wolven_hunt.cli simulate --config configs/games/classic_8.yaml --seed wolven-hunt-demo-seed-001

serve:
	uv run python -m wolven_hunt.cli serve --host 127.0.0.1 --port 7002

serve-prod:
	npm run build
	uv run python -m wolven_hunt.cli serve-prod --host 0.0.0.0 --port 7002

resimulate:
	uv run python -m wolven_hunt.cli resimulate --events $(FILE)
