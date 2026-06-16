.PHONY: format lint test docs

format:
	uv run ruff format .
	uv run ruff check --fix-only .

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy .

test:
	uv run pytest -m "not real_integration" tests/ --cov=src/acodex --cov-report=term-missing

docs:
	rm -rf docs/_build
	uv run --group docs sphinx-build -W -b html docs docs/_build/html
