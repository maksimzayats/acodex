# Contributing

Thanks for contributing to acodex.

acodex is a Python 3.10+ library with strict quality gates: Ruff (lint + format), mypy (strict),
and 100% test coverage.

## Setup (uv)

Install development and docs dependencies:

```bash
uv sync --group dev --group docs
```

## Quality gates

Format:

```bash
make format
```

Lint + type check:

```bash
make lint
```

Tests (coverage must stay at 100%):

```bash
make test
```

Docs:

```bash
uv run sphinx-build -W -b html docs docs/_build/html
```

## TypeScript SDK parity workflow

The vendored TypeScript SDK under `vendor/codex-ts-sdk/src/` is the source of truth for the public
surface. CI enforces parity via `tests/compatibility/`.

Common workflows:

- Vendor the latest stable upstream release:

  ```bash
  make vendor-ts-sdk-latest
  ```

- Vendor a specific release tag:

  ```bash
  make vendor-ts-sdk TAG="vX.Y.Z"
  ```

After vendoring, run the compatibility suite and fix any drift:

```bash
uv run pytest tests/compatibility/
```

If you intentionally add a Python-specific divergence, document it in `DIFFERENCES.md` and add an
explicit compatibility assertion in `tests/compatibility/` so the divergence stays stable.
