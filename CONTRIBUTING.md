# Contributing

Thanks for contributing to acodex.

acodex is a Python 3.10+ library with strict quality gates: Ruff for linting and formatting,
strict mypy, and 100% test coverage.

## Current SDK Direction

This branch focuses on a provisional async SDK for automating a running Codex desktop app.

Current constraints:

- Async client only.
- The high-level client is `AsyncCodexApp`.
- `AsyncCodexApp` is exported from the top-level `acodex` package.
- The client talks to the running desktop renderer through Chrome DevTools Protocol.
- The default CDP endpoint is `http://127.0.0.1:9222`.
- Read-only wrappers are the safest supported path.
- State-changing wrappers exist, but they mutate live Codex app state.

The user-facing README should stay focused on usage. Keep setup, implementation, and development
details here.

## Local Setup

Install development dependencies with uv:

```bash
uv sync --group dev
```

Docs have been removed from this branch for now and will be rebuilt later.

## Quality Gates

Format:

```bash
make format
```

Lint and type-check:

```bash
make lint
```

Run the CI-safe test suite:

```bash
make test
```

Coverage must remain at 100%.

## CDP Backend Notes

`AsyncCodexApp` composes a lower-level `CodexAppCdpBackend`. The backend:

- fetches CDP targets from `/json/list`;
- selects the Codex `app://` page target;
- connects to the target websocket;
- evaluates JavaScript through `Runtime.evaluate`;
- discovers renderer `codex_app` thread tools;
- invokes discovered tools through the renderer runtime.

The SDK client should expose end-user behavior, not CDP debugging internals. Do not add public
`AsyncCodexApp` properties for target metadata, discovery metadata, raw runtimes, or backend
internals.

## Configuration

Pass `CodexAppCdpSettings` for explicit CDP configuration:

```python
from acodex import AsyncCodexApp
from acodex.core.asyncio.cdp.settings import CodexAppCdpSettings

client = AsyncCodexApp(
    settings=CodexAppCdpSettings(endpoint="http://127.0.0.1:9222"),
)
```

Do not add separate shortcut parameters such as `AsyncCodexApp(endpoint=...)`. Keep CDP settings in
`CodexAppCdpSettings`.

Environment variables:

| Variable | Purpose |
| --- | --- |
| `ACODEX_CDP_ENDPOINT` | CDP HTTP endpoint. |
| `ACODEX_CDP_TARGET_URL` | Exact Codex app target URL to prefer. |
| `ACODEX_CDP_TARGET_URL_PREFIX` | App target URL prefix fallback. |
| `ACODEX_CDP_HTTP_TIMEOUT` | Timeout for CDP HTTP target discovery. |
| `ACODEX_CDP_RUNTIME_TIMEOUT` | Timeout for CDP runtime evaluation. |

## SDK Surface Guidelines

Direct methods are the intended SDK path:

- `list_threads(...)`
- `read_thread(...)`
- `create_thread(...)`
- `send_message_to_thread(...)`
- `fork_thread(...)`
- `set_thread_pinned(...)`
- `set_thread_archived(...)`
- `set_thread_title(...)`
- `handoff_thread(...)`

Public Python method names and option keys must use `snake_case`. The backend translates payloads to
the renderer's `camelCase` keys immediately before invocation.

`client.tools` is read-only and exists for advanced class-based usage. Prefer direct client methods
in README examples and user-facing guidance.

## Result Objects

Tool results currently provide typed attribute access and are backed by Pydantic models. Treat
Pydantic-specific methods such as `model_dump()` as a temporary implementation detail; the intended
long-term SDK shape is plain typed result objects.

## Live App Safety

These methods change the running Codex app state:

- `create_thread(...)`
- `send_message_to_thread(...)`
- `fork_thread(...)`
- `set_thread_pinned(...)`
- `set_thread_archived(...)`
- `set_thread_title(...)`
- `handoff_thread(...)`

Unit tests should use fakes and must not require a live Codex app. Do not run live mutating CDP
calls unless the user explicitly approves that exact action.
