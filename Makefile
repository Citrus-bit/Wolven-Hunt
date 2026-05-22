.PHONY: install lint format typecheck test test-fast cov simulate

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

cov:
	uv run pytest --cov=wolven_hunt --cov-report=term-missing

simulate:
	uv run python -m wolven_hunt.cli simulate --config configs/games/classic_8.yaml --seed wolven-hunt-demo-seed-001
