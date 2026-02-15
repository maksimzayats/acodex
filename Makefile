.PHONY: format lint test docs vendor-ts-sdk vendor-ts-sdk-latest

format:
	uv run ruff format .
	uv run ruff check --fix-only .

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy .

test:
	uv run pytest tests/ --cov=src/acodex --cov-report=term-missing

docs:
	rm -rf docs/_build
	uv run sphinx-build -b html docs docs/_build/html

vendor-ts-sdk:
	uv run python tools/vendor/fetch_codex_ts_sdk.py $(if $(TAG),--tag $(TAG),)

vendor-ts-sdk-latest:
	@tag="$$(uv run python tools/vendor/latest_codex_release.py --field release_tag)"; \
	echo "Latest stable Codex release: $$tag"; \
	$(MAKE) vendor-ts-sdk TAG="$$tag"
