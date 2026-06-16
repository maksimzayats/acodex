# acodex

acodex is under active redevelopment. The current branch contains an initial async CDP backend for
talking to a running Codex desktop app renderer through Chrome DevTools Protocol.

The old CLI/TypeScript-SDK-parity implementation has been removed from this branch.

## CDP backend

`CodexAppCdpClient` connects to a configurable CDP endpoint, defaults to
`http://127.0.0.1:9222`, finds the `app://-/index.html` page target, discovers the renderer's
dynamic `codex_app` thread tools, and invokes them through `Runtime.evaluate`.

Read-only wrappers are available for `list_threads()` and `read_thread(...)`. The client also
binds class-based tool objects under `client.tools`, for example
`client.tools.list_threads(...)`.

Configuration can be passed with `CodexAppCdpSettings` or environment variables:

- `ACODEX_CDP_ENDPOINT`
- `ACODEX_CDP_TARGET_URL`
- `ACODEX_CDP_TARGET_URL_PREFIX`
- `ACODEX_CDP_HTTP_TIMEOUT`
- `ACODEX_CDP_RUNTIME_TIMEOUT`

```python
from __future__ import annotations

import asyncio

from acodex import CodexAppCdpClient


async def main() -> None:
    async with CodexAppCdpClient() as client:
        threads = await client.list_threads(limit=5)
        thread = await client.read_thread(
            thread_id="019ed0be-fa81-7662-b15c-17472a4f440c",
            turn_limit=3,
            include_outputs=False,
        )
        print(threads.model_dump())
        print(thread.model_dump())


asyncio.run(main())
```

State-changing wrappers are available directly. Do not call them against a real Codex app unless
you intend to change app state.

```python
await client.set_thread_pinned(
    thread_id="019ed0be-fa81-7662-b15c-17472a4f440c",
    pinned=True,
)
```

Public Python methods and options stay snake_case. The backend translates to the renderer's
camelCase payload keys internally immediately before invocation.

## Development

Use uv for local tooling:

```bash
uv sync --group dev
make format
make lint
make test
```

## Disclaimer

It is independently maintained and is not affiliated with, sponsored by, or endorsed by OpenAI.
