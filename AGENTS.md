# Agent Notes for acodex

This repository is a Python 3.10+ library. Use strict linting, typing, and
testing standards. Prefer uv for all tooling.

## Quick commands

- Install deps (dev): `uv sync --group dev`
- Format: `make format`
- Lint (all): `make lint`
- Test (all): `make test`

## Build

- Build wheel/sdist: `uv build`
- Clean build artifacts manually if needed (no scripted clean target)

## Lint and type checks

- Always keep linting and type-checking clean; do not proceed with changes that introduce errors.
- Ruff lint: `uv run ruff check .`
- Ruff auto-fix (limited): `uv run ruff check --fix-only .`
- Ruff format: `uv run ruff format .`
- mypy (strict): `uv run mypy .`

## Tests

- Run all tests (coverage): `make test`
- Run a single test file: `uv run pytest tests/test_some.py`
- Run a single test: `uv run pytest tests/test_some.:test_some`
- Run tests with keyword filter: `uv run pytest -k "dependency" tests/`
- Coverage (recommended for new work):
  `uv run pytest tests/ --cov=src/acodex --cov-report=term-missing`

## Repo structure

## Style and formatting

- Just run `make format` to apply all formatting rules (Ruff and any additional formatting).
- Line length: 100 (Ruff).
- Quotes: double quotes (Ruff format).
- Indent: 4 spaces.
- Format with Ruff before linting.
- Use ASCII unless the file already contains non-ASCII characters.

## Imports

- No relative imports in library code (Ruff tidy-imports bans them).
- Prefer explicit imports from `acodex` modules.
- Combine `as` imports when appropriate (`combine-as-imports = true`).
- Avoid unused imports; `__init__.py` is allowed to re-export.

## Typing and types

- Always use __future__ annotations for forward references and to enable postponed evaluation of annotations.
- Python minimum version is 3.10 with future annotation (use `|` unions, `list[str]`, etc.).
- All new public APIs must be fully typed.
- mypy is strict; keep types precise and avoid `Any`.
- If `Any` is unavoidable, document why and keep scope minimal.
- Do not use generic `object` annotations when domain types already exist (for example, prefer `CodexConfigObject` / `CodexConfigValue`).
- Use `typing.Protocol` or `collections.abc` for public contracts.
- Prefer `Final` for constants that should not change.

## Naming conventions

- Classes: `PascalCase`.
- Functions and variables: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Public API names should be stable and descriptive.
- Test names should describe the behavior and expectation.

## Error handling

- Prefer explicit error messages over implicit failures.
- Avoid catching `Exception` unless re-raising with context.
- When adding new errors, update tests and docs/examples as needed.

## Docstrings and docs

## Testing guidelines

- Aim for maximum coverage and edge cases for all new features.
- Maintain 100% coverage overall; every change must keep coverage at 100%.
- Tests live in `tests/` and mirror module naming when possible.
- Use pytest fixtures from `tests/conftest.py` for shared setup.
- Prefer small, focused tests over large integration tests.
- Keep tests deterministic; avoid time-based assertions unless necessary.

## Quality gates

- Always ensure linting and type-checking run clean with no errors.
- Every new change must preserve 100% test coverage.
- After making changes, always run `make lint` and `make test` and report results.

## Ruff configuration highlights

- `select = ["ALL"]` with targeted ignores.
- Tests allow `assert`, unused args, and some pytest patterns.

## Agent behavior

- Do not add new lint ignores without justification.
- Preserve existing formatting and file organization.
- Update or add tests whenever behavior changes.

## SDK parity notes (important)

- For TS-SDK-shaped Python surface areas, use `TypedDict` for input-only option/argument payloads passed into methods (for example: `CodexOptions`, `ThreadOptions`, `TurnOptions`, `CodexExecArgs`, and input unions).
- For return/event/item payload models, prefer `@dataclass(frozen=True, slots=True)` instead of `TypedDict`.
- Keep discriminant `type` values as typed `Literal[...]` fields on return dataclasses (typically fixed defaults, non-init).
- Keep public API method names and option keys snake_case only; do not add camelCase aliases unless explicitly requested.
- The TypeScript SDK (`_ts_sdk/src`) is the source of truth for features and behavior.
- Target one-to-one feature parity with the TypeScript SDK for all public APIs.
- Pythonic deviations are allowed only when explicitly documented in `differences.md`.
- Before implementing any feature or behavior change, check `differences.md` first and follow existing documented divergences.
- If a new Pythonic divergence is needed, document it in `differences.md` in the same change.
