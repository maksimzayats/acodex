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

## 2) Return models use dataclasses

- TypeScript SDK models events and items as structural object types.
- Python SDK models events and items as `@dataclass(frozen=True, slots=True)` instances.

Rationale:
- This provides stronger typed object ergonomics in Python while preserving JSON field names.
- It keeps input option payloads as `TypedDict`, but makes returned models explicit value objects.

Usage implication:
- Access fields via attributes (for example, `event.type`, `item.id`) on returned objects.

## 3) Dual sync and async client surfaces

- TypeScript SDK exposes an async-only client surface.
- Python SDK exposes both sync (`Codex`, `Thread`) and async (`AsyncCodex`, `AsyncThread`)
  surfaces.

Rationale:
- Python users commonly need both synchronous and asynchronous integration styles.

Usage implication:
- Choose sync or async API families consistently within a call path.
