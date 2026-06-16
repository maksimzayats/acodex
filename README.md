# acodex

**Python automation for the Codex desktop app.**

acodex is a Python 3.10+ library for automating a running Codex desktop app
from typed async Python code. It connects to the desktop renderer through Chrome
DevTools Protocol, discovers the available thread tools, and exposes a small
SDK-style surface for reading, creating, updating, and handing off Codex threads.

[Install](#install) ·
[Contribute](CONTRIBUTING.md)

## Key Features

- **Async Codex desktop client.** Use `AsyncCodexApp` to work with a local
  Codex desktop session from Python.
- **Typed thread operations.** List, read, create, fork, update, archive, pin,
  title, message, and hand off threads through explicit methods.
- **CDP-backed local automation.** acodex talks to the running desktop renderer
  over Chrome DevTools Protocol and keeps CDP details behind the public client.

## Install

Install acodex into your project:

```sh
uv add acodex
```

acodex expects a running Codex desktop app with a reachable Chrome DevTools
Protocol endpoint. The default endpoint is `http://127.0.0.1:9222`.

List recent threads:

```python
from __future__ import annotations

import asyncio

from acodex import AsyncCodexApp


async def main() -> None:
    async with AsyncCodexApp() as client:
        threads = await client.list_threads(limit=5)

    for thread in threads.threads:
        print(thread.id, thread.title)


asyncio.run(main())
```

## What You Get

- A Python SDK-style surface for automating a live Codex desktop app.
- Typed async methods for common thread workflows.
- Read-only operations for inspecting app state.
- State-changing operations for intentional live app updates.
- Configuration through `CodexAppCdpSettings` and `ACODEX_*` environment
  variables when the default CDP endpoint is not enough.

## Why acodex

Codex desktop is most useful when it can stay close to local project context,
threads, and handoffs. acodex gives Python tools and automation scripts a typed
way to work with that running app while keeping the browser-runtime plumbing out
of user code.

State-changing methods mutate the live Codex app. Use them only when you intend
to change app state.

## Contributing

Developer setup, architecture notes, SDK direction, and quality gates live in
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

acodex is released under the [MIT License](LICENSE).

acodex is independently maintained and is not affiliated with, sponsored by, or
endorsed by OpenAI.
