# Contributing

Thank you for improving acodex. This guide keeps contributor workflow and
technical detail out of the README so the README can stay focused on users.

## What Belongs Where

- `README.md`: what acodex does, why it is useful, quick start, core CLI usage,
  configuration essentials, contribution link, license, and disclaimer.
- `CONTRIBUTING.md`: development setup, architecture, quality gates, testing,
  pull request expectations, and documentation maintenance.
- `AGENTS.md`: short instructions for AI agents working in this repository.

If a detail only matters while changing the project, put it here instead of in
the README.

## Development Setup

Prerequisites:

- Python 3.10 or newer.
- `uv`; see the [official install guide](https://docs.astral.sh/uv/getting-started/installation/).
- macOS with Codex.app installed for manual desktop testing. The relaunch flow
  expects `/Applications/Codex.app` by default; set `ACODEX_CODEX_APP_PATH` if
  yours is elsewhere.

Clone the repository and install all dependency groups:

```sh
git clone https://github.com/maksimzayats/acodex.git
cd acodex
uv sync --all-groups
```

Check the local CLI:

```sh
uv run acodex --help
uv run acodex doctor
```

For manual Codex desktop testing, initialize config and run the managed bridge:

```sh
uv run acodex config init
uv run acodex codex status
uv run acodex codex relaunch --yes
uv run acodex server start
uv run acodex tools list
uv run acodex server stop
```

`uv run acodex codex relaunch --yes` starts or restarts Codex so acodex can
reach the default CDP endpoint, `http://127.0.0.1:45217`.

## Configuration Reference

acodex reads JSON config from `~/.acodex/config.json` unless `ACODEX_CONFIG`
points to another file. The config file is created with `acodex config init` and
can be inspected with `acodex config show`.

Configuration precedence, from highest to lowest, is:

1. CLI flags passed to commands that support runtime overrides.
2. `ACODEX_*` environment variables.
3. The config file.
4. Built-in defaults.

Full defaults matrix:

| Section | Key | Default | Environment override | CLI override |
| --- | --- | --- | --- | --- |
| `server` | `host` | `127.0.0.1` | `ACODEX_SERVER_HOST` | `acodex server start --host` |
| `server` | `port` | `45218` | `ACODEX_SERVER_PORT` | `acodex server start --port` |
| `codex` | `app_path` | `/Applications/Codex.app` | `ACODEX_CODEX_APP_PATH` | `acodex codex relaunch --app` |
| `codex` | `cdp_host` | `127.0.0.1` | `ACODEX_CODEX_APP_CDP_HOST` | None |
| `codex` | `cdp_port` | `45217` | `ACODEX_CODEX_APP_CDP_PORT` | `acodex codex relaunch --port` |
| `codex` | `request_timeout` | `10.0` | `ACODEX_CODEX_APP_CDP_REQUEST_TIMEOUT` | None |
| `codex` | `launch_timeout` | `20.0` | None | None |
| `bridge` | `host_id` | `local` | `ACODEX_CODEX_APP_BRIDGE_HOST_ID` | None |
| `bridge` | `source_thread_id` | `null` | `ACODEX_CODEX_APP_BRIDGE_SOURCE_THREAD_ID` | None |

`ACODEX_CONFIG` changes the config file path; it does not set a config value.
The managed server exposes `/healthz` and `/mcp` on the configured server host
and port.

## Quality Gates

Run these before opening a pull request:

```sh
make format
make lint
make test
```

The Makefile expands to:

```sh
uv run ruff format .
uv run ruff check --fix-only .
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest -m "not real_integration" tests/ --cov=src/acodex --cov-report=term-missing
```

Keep unit tests independent from a live Codex app. Tests that require a real
local Codex setup must be marked with `real_integration`. Run them explicitly
with:

```sh
ACODEX_RUN_REAL_INTEGRATION=1 uv run pytest -m real_integration tests/
```

## Architecture

Keep responsibilities narrow and explicit:

- `src/acodex/cli/`: Typer command wiring, CLI orchestration, and terminal
  presentation.
- `src/acodex/config.py`: config loading, precedence, defaults, and validation.
- `src/acodex/core/codex_app/`: CDP connection, renderer asset discovery, and
  Codex desktop tool bridging.
- `src/acodex/core/mcp_tools.py`: small JSON-RPC client used by the CLI to call
  the managed MCP server.
- `src/acodex/http/`: FastAPI routes and MCP JSON-RPC request handling.
- `src/acodex/ioc/`: dependency injection container registration.
- `tests/`: unit, CLI, HTTP, MCP, and opt-in integration coverage.

Prefer dependency injection for shared services, stateful collaborators, and
I/O boundaries. Main feature logic should usually live in focused classes or
dataclasses with injected dependencies. Use module-level functions for small
pure helpers, validation, and format conversion where a class would add noise.

Do not bypass layers for convenience. For example, CLI commands should not talk
directly to the Codex renderer when the managed MCP or bridge layer owns that
responsibility.

## Pull Request Checklist

- The change is scoped to one clear behavior or documentation improvement.
- New behavior has tests at the right layer.
- Existing behavior is preserved unless the PR explicitly changes it.
- CLI output remains stable, readable, and covered by tests when changed.
- README claims match the current code and installed commands.
- Technical setup or maintenance details are in this file, not the README.
- Agent-only implementation instructions are in `AGENTS.md`, not the README.

## Documentation Rules

Keep documentation current with the code in the same change. Remove stale
sections instead of leaving historical instructions in place.

Use the README for a fast first impression: plain-language purpose, quick start,
feature highlights, support path, and license. Move deeper workflows,
architecture notes, test commands, and contributor expectations here.

When adding examples, verify command names and flags against `uv run acodex
--help` or the relevant subcommand help.

## Reporting Issues

Open issues at <https://github.com/maksimzayats/acodex/issues>. Include:

- What you tried.
- What you expected.
- What happened instead.
- Your OS, Python version, acodex version, and Codex desktop/CDP setup.
- Relevant `acodex doctor` output, with secrets removed.
