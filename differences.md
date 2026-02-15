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

## 4) Cancellation error type

- TypeScript SDK surfaces cancellation through generic thrown errors from abort behavior.
- Python SDK raises `CodexCancelledError` when `TurnOptions.signal` is set before or during a run.

Rationale:
- It gives Python callers a precise exception type for control flow.
- It keeps cancellation distinct from process failures and stream parsing failures.

Usage implication:
- Catch `CodexCancelledError` when implementing cancellation-aware loops.

## 5) Codex executable discovery

- TypeScript SDK resolves a bundled CLI binary from npm optional dependencies.
- Python SDK resolves `codex` from `PATH` by default, unless `codex_path_override` is provided.

Rationale:
- Python packaging does not bundle the same platform-specific npm artifacts.
- `PATH` lookup aligns with common Python CLI integration patterns.

Usage implication:
- Ensure `codex` is installed and discoverable on `PATH`, or pass `codex_path_override`.
