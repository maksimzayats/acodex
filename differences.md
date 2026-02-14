# Differences from TypeScript SDK

## 1) Cancellation primitive

- TypeScript SDK uses `AbortController` and `AbortSignal`.
- Python SDK uses `threading.Event` and `asyncio.Event` through `TurnOptions.signal`.

Rationale:
- This keeps the API familiar for Python users.
- It avoids adding custom controller classes for a core standard-library capability.

Sync example:

```python
import threading

from acodex import Codex

client = Codex()
thread = client.start_thread()
cancel_event = threading.Event()

streamed = thread.run_streamed("Hello", signal=cancel_event)
cancel_event.set()
```

Async example:

```python
import asyncio

from acodex import AsyncCodex


async def main() -> None:
    client = AsyncCodex()
    thread = client.start_thread()
    cancel_event = asyncio.Event()

    streamed = await thread.run_streamed("Hello", signal=cancel_event)
    cancel_event.set()


asyncio.run(main())
```
