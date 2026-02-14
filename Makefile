.PHONY: format lint test

format:
	uv run ruff format .
	uv run ruff check --fix-only .

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy .

test:
	uv run pytest tests/ --cov=src/acodex --cov-report=term-missing
