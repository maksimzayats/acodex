# Differences from the TypeScript SDK

The vendored TypeScript SDK under `vendor/codex-ts-sdk/src/` is the source of truth for the public
surface. The Python SDK aims for one-to-one feature parity while applying a small number of
intentional Python-specific adaptations.

These divergences are:

- documented here
- asserted in `tests/compatibility/` (so changes fail loudly)

For the broader compatibility policy and test coverage, see `COMPATIBILITY.md`.

## 1) Name casing: camelCase (TS) -> snake_case (Python)

TypeScript API surface uses camelCase. Python uses snake_case across public methods, options keys,
and dataclass fields.

Examples:

- TS `Codex.startThread(options?)` -> Python `Codex.start_thread(**thread_options)`
- TS `Thread.runStreamed(input, turnOptions?)` -> Python `Thread.run_streamed(input, **turn_options)`
- TS `Turn.finalResponse` -> Python `Turn.final_response`

References:

- TS: `vendor/codex-ts-sdk/src/codex.ts`, `vendor/codex-ts-sdk/src/thread.ts`,
  `vendor/codex-ts-sdk/src/threadOptions.ts`
- Python: `src/acodex/codex.py`, `src/acodex/thread.py`, `src/acodex/types/turn.py`,
  `src/acodex/types/thread_options.py`
- Tests: `tests/compatibility/test_ts_class_surface_compat.py`,
  `tests/compatibility/test_ts_thread_types_compat.py`,
  `tests/compatibility/test_ts_thread_options_compat.py`

## 2) Options are passed as kwargs (Python) instead of an options object (TS)

TypeScript generally accepts an options object parameter (or default `{}`), for example:

- TS: `constructor(options: CodexOptions = {})`
- TS: `startThread(options: ThreadOptions = {})`
- TS: `run(input: Input, turnOptions: TurnOptions = {})`

Python exposes these options as keyword arguments using `TypedDict` + `Unpack[...]`:

- Python: `Codex(**options: Unpack[CodexOptions])`
- Python: `Codex.start_thread(**thread_options: Unpack[ThreadOptions])`
- Python: `Thread.run(input: Input, **turn_options: Unpack[TurnOptions])`

References:

- TS: `vendor/codex-ts-sdk/src/codex.ts`, `vendor/codex-ts-sdk/src/thread.ts`,
  `vendor/codex-ts-sdk/src/codexOptions.ts`, `vendor/codex-ts-sdk/src/threadOptions.ts`,
  `vendor/codex-ts-sdk/src/turnOptions.ts`
- Python: `src/acodex/codex.py`, `src/acodex/thread.py`, `src/acodex/types/codex_options.py`,
  `src/acodex/types/thread_options.py`, `src/acodex/types/turn_options.py`
- Tests: `tests/compatibility/test_ts_codex_options_compat.py`,
  `tests/compatibility/test_ts_thread_options_compat.py`,
  `tests/compatibility/test_ts_turn_options_compat.py`,
  `tests/compatibility/test_ts_class_surface_compat.py`

## 3) Cancellation primitive: AbortSignal (TS) -> Event (Python)

- TypeScript: `TurnOptions.signal?: AbortSignal` (`vendor/codex-ts-sdk/src/turnOptions.ts`)
- Python: `TurnSignal = threading.Event | asyncio.Event` and `TurnOptions.signal: NotRequired[TurnSignal]`
  (`src/acodex/types/turn_options.py`)

Rationale:

- Uses standard-library cancellation primitives familiar to Python users.
- Avoids introducing custom controller types for a common capability.

Compatibility assertion:

- Test: `tests/compatibility/test_ts_turn_options_compat.py`

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

## 4) Return models use dataclasses (Python) instead of structural object types (TS)

- TypeScript events/items are structural object types (`vendor/codex-ts-sdk/src/events.ts`,
  `vendor/codex-ts-sdk/src/items.ts`)
- Python events/items are explicit `@dataclass(frozen=True, slots=True)` models
  (`src/acodex/types/events.py`, `src/acodex/types/items.py`)
- TypeScript `Turn` is a structural object type (`vendor/codex-ts-sdk/src/thread.ts`)
- Python `Turn` is a dataclass with snake_case fields (`src/acodex/types/turn.py`)

Rationale:

- Improves Python ergonomics (attribute access, explicit value objects).
- Keeps option payloads as `TypedDict`, but makes returned values explicit models.

Compatibility assertions:

- Tests: `tests/compatibility/test_ts_events_compat.py`, `tests/compatibility/test_ts_items_compat.py`,
  `tests/compatibility/test_ts_thread_types_compat.py`

Usage implication:

- Access fields via attributes (for example, `event.type`, `item.id`, `turn.final_response`).

## 5) Dual sync and async client surfaces (Python), async-only surface (TS)

- TypeScript exposes async-only behavior (e.g. `Thread.runStreamed(...)` returns a `Promise<...>` and
  streams an `AsyncGenerator<ThreadEvent>`).
- Python exposes both:
  - sync: `Codex`, `Thread`
  - async: `AsyncCodex`, `AsyncThread`

Rationale:

- Python users commonly need synchronous and asynchronous integration styles.

Compatibility assertions:

- Tests: `tests/compatibility/test_sdk_exports.py` (Python-only async exports allowed),
  `tests/compatibility/test_ts_class_surface_compat.py` (TS async behavior supported via `AsyncThread`)

Usage implication:

- Choose sync or async API families consistently within a call path.

## 6) Cancellation error type (Python)

- TypeScript surfaces cancellation through generic thrown errors from abort behavior.
- Python raises `CodexCancelledError` when `TurnOptions.signal` is set before or during a run.

References:

- Python exceptions: `src/acodex/exceptions.py`
- Turn cancellation option: `src/acodex/types/turn_options.py`

Rationale:

- Provides a precise exception type for control flow.
- Keeps cancellation distinct from process failures and parsing failures.

Usage implication:

- Catch `CodexCancelledError` when implementing cancellation-aware loops.

## 7) Codex executable discovery (PATH vs bundled binary)

- TypeScript resolves a bundled CLI binary from npm optional dependencies.
- Python resolves `codex` from `PATH` by default, unless `codex_path_override` is provided.

References:

- TS option: `codexPathOverride` in `vendor/codex-ts-sdk/src/codexOptions.ts`
- Python option: `codex_path_override` in `src/acodex/types/codex_options.py`
- Python exec setup: `src/acodex/codex.py`, `src/acodex/exec.py`, `src/acodex/_internal/exec.py`

Rationale:

- Python packaging does not bundle the same platform-specific npm artifacts.
- PATH lookup aligns with common Python CLI integration patterns.

Usage implication:

- Ensure `codex` is installed and discoverable on `PATH`, or pass `codex_path_override`.

## 8) Output schema typing is narrower in Python

- TypeScript: `TurnOptions.outputSchema?: unknown` (`vendor/codex-ts-sdk/src/turnOptions.ts`)
- Python: `TurnOptions.output_schema: NotRequired[dict[str, JsonValue]]` (JSON-object shape),
  `OutputSchemaInput = JsonObject` (`src/acodex/types/turn_options.py`)

Rationale:

- Encourages passing a JSON-serializable object (what the CLI ultimately consumes).
- Enables stronger typing for Python callers while still being TS-compatible with `unknown`.

Compatibility assertion:

- Test: `tests/compatibility/test_ts_turn_options_compat.py` (accepts TS `unknown` as compatible with
  narrower Python typing)

## 9) Streamed result exposes a completed turn property in Python

- TypeScript streamed flow returns events and leaves reduction to SDK internals in `run()`.
- Python streamed result models expose `streamed.result` (sync and async) after the stream is fully
  consumed.

References:

- Python models: `src/acodex/types/turn.py`
- Python run flow: `src/acodex/thread.py`

Usage implication:

- Consume `streamed.events` completely, then access `streamed.result`.
- Accessing `streamed.result` before full consumption raises
  `CodexThreadStreamNotConsumedError`.
