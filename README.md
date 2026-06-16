# acodex

Python automation for the Codex desktop app.

## Usage

List recent threads:

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
async def read_thread() -> None:
    async with AsyncCodexApp() as client:
        thread = await client.read_thread(
            thread_id="019ed0be-fa81-7662-b15c-17472a4f440c",
            turn_limit=3,
            include_outputs=False,
        )

    print(thread.thread.title)
```

Pin a thread:

```python
async def pin_thread() -> None:
    async with AsyncCodexApp() as client:
        await client.set_thread_pinned(
            thread_id="019ed0be-fa81-7662-b15c-17472a4f440c",
            pinned=True,
        )
```

State-changing methods mutate the live Codex app. Use them only when you intend to change app
state.

## License

Apache-2.0. See `LICENSE`.

acodex is independently maintained and is not affiliated with, sponsored by, or endorsed by OpenAI.
