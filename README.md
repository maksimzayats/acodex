# acodex

Python experiments for automating the Codex desktop app.

This branch currently focuses on a provisional async SDK that talks to a running Codex desktop
renderer through Chrome DevTools Protocol (CDP). The API is intentionally narrow while the SDK shape
is still settling.

## Status

- Python 3.10+
- Async client only
- CDP endpoint default: `http://127.0.0.1:9222`
- Public top-level `acodex` re-exports are intentionally disabled for now
- Read-only thread wrappers are the safest supported path
- State-changing wrappers exist, but mutate the live Codex app

## Prerequisites

You need a running Codex desktop app with CDP enabled and reachable at the configured endpoint.

To verify the default endpoint:

```bash
curl http://127.0.0.1:9222/json/list
```

The client selects the Codex `app://` page target from that target list and invokes the renderer's
`codex_app` thread tools through `Runtime.evaluate`.

## Installation

For local development from this checkout:

```bash
uv sync --group dev
```

The package metadata lives in `pyproject.toml`; prefer `uv` for all local tooling.

## Quickstart

```python
from __future__ import annotations

import asyncio

from acodex.adapters.sdk.asyncio.client import AsyncCodexApp


async def main() -> None:
    async with AsyncCodexApp() as client:
        threads = await client.list_threads(limit=5)

        for thread in threads.threads:
            print(thread.id, thread.title)


asyncio.run(main())
```

Read a thread:

```python
async with AsyncCodexApp() as client:
    thread = await client.read_thread(
        thread_id="019ed0be-fa81-7662-b15c-17472a4f440c",
        turn_limit=3,
        include_outputs=False,
    )
    print(thread.thread.title)
```

## Configuration

Pass `CodexAppCdpSettings` for explicit configuration:

```python
from acodex.adapters.sdk.asyncio.client import AsyncCodexApp
from acodex.core.asyncio.cdp.settings import CodexAppCdpSettings

client = AsyncCodexApp(
    settings=CodexAppCdpSettings(endpoint="http://127.0.0.1:9222"),
)
```

Environment variables are also supported:

| Variable | Purpose |
| --- | --- |
| `ACODEX_CDP_ENDPOINT` | CDP HTTP endpoint. |
| `ACODEX_CDP_TARGET_URL` | Exact Codex app target URL to prefer. |
| `ACODEX_CDP_TARGET_URL_PREFIX` | App target URL prefix fallback. |
| `ACODEX_CDP_HTTP_TIMEOUT` | Timeout for CDP HTTP target discovery. |
| `ACODEX_CDP_RUNTIME_TIMEOUT` | Timeout for CDP runtime evaluation. |

## SDK Surface

Import the provisional async client directly:

```python
from acodex.adapters.sdk.asyncio.client import AsyncCodexApp
```

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

Public Python method names and option keys use `snake_case`. The CDP backend translates payloads to
the renderer's `camelCase` keys immediately before invocation.

`client.tools` exposes read-only class-based tool objects for advanced callers that need to pass a
specific tool object around. Prefer direct client methods unless you have that need.

## Live App Mutations

These methods change the running Codex app state:

- `create_thread(...)`
- `send_message_to_thread(...)`
- `fork_thread(...)`
- `set_thread_pinned(...)`
- `set_thread_archived(...)`
- `set_thread_title(...)`
- `handoff_thread(...)`

Call them only when you intend to mutate the live app.

## Result Objects

Tool results currently provide typed attribute access and are backed by Pydantic models. Treat
Pydantic-specific methods such as `model_dump()` as a temporary implementation detail; the intended
long-term SDK shape is plain typed result objects.

## Development

```bash
make format
make lint
make test
```

Run the real Codex integration suite only when a live local Codex setup is available:

```bash
ACODEX_RUN_REAL_INTEGRATION=1 make test-real-integration
```

## License

Apache-2.0. See `LICENSE`.

acodex is independently maintained and is not affiliated with, sponsored by, or endorsed by OpenAI.
