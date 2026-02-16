# TypeScript <-> Python SDK Compatibility

This repository vendors the TypeScript SDK and treats it as the source of truth for the public
surface. We enforce compatibility by running a Python-only test suite that parses the vendored TS
sources (no Node / tsserver / tsc required) and asserts that the Python SDK exposes an equivalent
public API surface.

If a TypeScript contract changes (new exported type, new option key, discriminator change, etc.),
the compatibility tests should fail loudly and point to the mismatch.

## Source of truth

- TypeScript SDK (vendored): `vendor/codex-ts-sdk/src/`
  - Export index: `vendor/codex-ts-sdk/src/index.ts`
  - Models:
    - Events: `vendor/codex-ts-sdk/src/events.ts`
    - Items: `vendor/codex-ts-sdk/src/items.ts`
  - Options payloads:
    - `vendor/codex-ts-sdk/src/codexOptions.ts`
    - `vendor/codex-ts-sdk/src/threadOptions.ts`
    - `vendor/codex-ts-sdk/src/turnOptions.ts`
  - Thread types + class surface:
    - `vendor/codex-ts-sdk/src/thread.ts`
  - Client class surface:
    - `vendor/codex-ts-sdk/src/codex.ts`

## What we consider “public surface”

Compatibility is enforced for public exports and their directly referenced contracts:

1. **Exports**
   - TS exported names from `vendor/codex-ts-sdk/src/index.ts`
   - Python exported names from `src/acodex/__init__.py`
   - Test: `tests/compatibility/test_sdk_exports.py`

2. **Return models**
   - TS: `events.ts`, `items.ts`, `thread.ts` (`Turn`, etc.)
   - Python: dataclasses and type aliases in `src/acodex/types/`
   - Tests:
     - `tests/compatibility/test_ts_events_compat.py`
     - `tests/compatibility/test_ts_items_compat.py`
     - `tests/compatibility/test_ts_thread_types_compat.py`

3. **Input-only option payloads**
   - TS: `codexOptions.ts`, `threadOptions.ts`, `turnOptions.ts`
   - Python: `TypedDict` payloads in `src/acodex/types/`
   - Tests:
     - `tests/compatibility/test_ts_codex_options_compat.py`
     - `tests/compatibility/test_ts_thread_options_compat.py`
     - `tests/compatibility/test_ts_turn_options_compat.py`

4. **Primary classes**
   - TS: `export class Codex` (`codex.ts`), `export class Thread` (`thread.ts`)
   - Python: `src/acodex/codex.py`, `src/acodex/thread.py`
   - Test: `tests/compatibility/test_ts_class_surface_compat.py`

## Documented divergences

All intentional Python deviations from the TypeScript SDK must be documented in `DIFFERENCES.md`
and asserted in compatibility tests.

Current enforced divergences:

- Cancellation primitive:
  - TS: `TurnOptions.signal?: AbortSignal` in `vendor/codex-ts-sdk/src/turnOptions.ts`
  - Python: `TurnSignal = threading.Event | asyncio.Event` and `TurnOptions.signal` in
    `src/acodex/types/turn_options.py`
  - Doc: `DIFFERENCES.md` (“Cancellation primitive”)
  - Test: `tests/compatibility/test_ts_turn_options_compat.py`

- Sync + async dual surface:
  - TS is async-first (e.g. `Thread.runStreamed()` returns a `Promise<StreamedTurn>` and streams
    an `AsyncGenerator<ThreadEvent>`).
  - Python provides both sync (`Codex`, `Thread`) and async (`AsyncCodex`, `AsyncThread`) surfaces
    while still supporting the TS behavior (async streaming via `AsyncThread.run_streamed`).
  - Doc: `DIFFERENCES.md` (“Dual sync and async client surfaces”)
  - Test: `tests/compatibility/test_ts_class_surface_compat.py`

- Python-only typed structured output:
  - TS `Thread.run` / `runStreamed` do not expose `outputType`, and TS `Turn` does not include
    `structuredResponse`.
  - Python adds optional `output_type` parameters on sync/async `run` + `run_streamed`, plus
    `Turn.structured_response` (backed by Python-only `Turn.structured_response_factory`).
  - Doc: `DIFFERENCES.md` (“Python-only typed structured output”)
  - Tests:
    - `tests/compatibility/test_ts_thread_types_compat.py`
    - `tests/compatibility/test_ts_class_surface_compat.py`

If you add a new divergence, update `DIFFERENCES.md` and add/adjust a compatibility assertion for
it in `tests/compatibility/`.

## Name mapping (TS -> Python)

The TypeScript SDK uses camelCase member names and keys; the Python SDK uses snake_case.

Rule:
- `fooBarBaz` (TS) maps to `foo_bar_baz` (Python)

Implementation:
- `tests/compatibility/_assertions.py` provides `camel_to_snake()` and tests use it consistently.

Where it is applied:
- Options key parity tests (TS object types -> Python `TypedDict` keys)
  - `tests/compatibility/test_ts_codex_options_compat.py`
  - `tests/compatibility/test_ts_thread_options_compat.py`
  - `tests/compatibility/test_ts_turn_options_compat.py`
- Thread “Turn” property `finalResponse` (TS) -> `final_response` (Python)
  - TS: `vendor/codex-ts-sdk/src/thread.ts`
  - Python: `src/acodex/types/turn.py`
  - Test: `tests/compatibility/test_ts_thread_types_compat.py`
- Class method surface (e.g. `startThread` -> `start_thread`, `runStreamed` -> `run_streamed`)
  - TS: `vendor/codex-ts-sdk/src/codex.ts`, `vendor/codex-ts-sdk/src/thread.ts`
  - Python: `src/acodex/codex.py`, `src/acodex/thread.py`
  - Test: `tests/compatibility/test_ts_class_surface_compat.py`

## Type mapping (TS -> Python)

The compatibility suite checks that Python type hints are compatible with TS type expressions using
subset parsing + structural comparisons.

### Primitive mapping

- `string` -> `str`
- `boolean` -> `bool`
- `number` -> `int` (Python may use `int | float`, and tests accept either for TS `number`)
- `null` -> `None` (represented as `T | null` in TS, `T | None` in Python)
- `unknown` -> Python may be `object` or any narrower type (tests accept narrower types)

### Collections and unions

- `T[]` -> `list[T]`
- `A | B` -> Python union (order-insensitive)

### External / unresolvable identifiers

If a TS identifier cannot be resolved to an exported type within the Python module resolver for a
given test, it is treated as “external” and is compatible with Python `object` (or `list[object]`
for arrays).

Example:
- TS `McpContentBlock[]` (from external MCP SDK) in `vendor/codex-ts-sdk/src/items.ts`
- Python maps it to `list[object]` in `src/acodex/types/items.py` (`McpToolCallResult.content`)
- Verified by `tests/compatibility/test_ts_items_compat.py`

### TypedDict optionality

TS uses `?` for optional properties in option payload objects; Python represents this via
`typing_extensions.NotRequired[...]` inside `TypedDict` definitions.

Notes:
- In `src/acodex/types/*_options.py`, `NotRequired` is imported under `TYPE_CHECKING` so runtime
  `__required_keys__` may not reflect “optional-only”. The tests therefore evaluate annotations via
  `typing.get_type_hints(..., include_extras=True, localns={"NotRequired": NotRequired, ...})` and
  then assert the presence of `NotRequired[...]` wrappers.

Tests:
- `tests/compatibility/test_ts_codex_options_compat.py`
- `tests/compatibility/test_ts_thread_options_compat.py`
- `tests/compatibility/test_ts_turn_options_compat.py`

## How compatibility is enforced (tooling + tests)

### Test data location

- TS SDK root: `vendor/codex-ts-sdk/src/`
- Python types: `src/acodex/types/`
- Python classes: `src/acodex/codex.py`, `src/acodex/thread.py`
- Compatibility tests: `tests/compatibility/`

Helper that defines vendor paths:
- `tests/compatibility/vendor_ts_sdk.py`

### TS parsing utilities (Python-only)

1. Export extraction (re-exports from `index.ts`)
   - `tools/compatibility/get_ts_exports.py`
   - Used by: `tests/compatibility/test_sdk_exports.py`

2. Exported type-alias parser (objects + simple unions)
   - `tools/compatibility/ts_type_alias_parser.py`
   - Provides:
     - `parse_exported_type_aliases()` for:
       - object type aliases (e.g. `export type Usage = { ... }`)
       - string-literal unions (e.g. `export type ApprovalMode = "never" | ...`)
       - identifier unions (e.g. `export type ThreadEvent = | Foo | Bar`)
     - `extract_exported_type_alias_rhs()` for aliases whose RHS requires more detail than the
       “object or union of identifiers” model (e.g. `Input`, `UserInput`, recursive config types).
   - Used by:
     - `tests/compatibility/test_ts_events_compat.py`
     - `tests/compatibility/test_ts_items_compat.py`
     - `tests/compatibility/test_ts_codex_options_compat.py`
     - `tests/compatibility/test_ts_thread_options_compat.py`
     - `tests/compatibility/test_ts_turn_options_compat.py`
     - `tests/compatibility/test_ts_thread_types_compat.py`

3. TS type-expression parser (subset)
   - `tools/compatibility/ts_type_expr.py`
   - Parses the subset currently used by the vendored SDK:
     - primitives (`string`, `number`, `boolean`, `unknown`, `null`)
     - string literals (`"foo"`)
     - identifiers
     - arrays (`T[]`)
     - unions (`A | B | ...`, including leading `|` formatting)
     - generics (e.g. `Record<string, string>`, `AsyncGenerator<ThreadEvent>`)
     - object types with:
       - named properties (`foo?: string`)
       - index signatures (`{ [key: string]: CodexConfigValue }`)
   - Used by the new options/type-parity tests and by events/items field type assertions.

4. TS class surface extractor (narrow)
   - `tools/compatibility/ts_class_parser.py`
   - Extracts exported class **public instance** methods and getters:
     - excludes private/protected members
     - excludes static members
     - excludes constructor
     - only matches declarations at class top level (avoids matching `if (...)` blocks)
   - Used by: `tests/compatibility/test_ts_class_surface_compat.py`

### Python-side structural assertions

Central assertion helpers:
- `tests/compatibility/_assertions.py`

Key helpers:
- `camel_to_snake()` (applied uniformly)
- `unwrap_not_required()` (for `TypedDict` fields)
- `dataclass_field_required()` (required vs optional fields in dataclasses)
- `assert_ts_expr_compatible()` (TS AST -> Python hint compatibility)

Resolver strategy:
- Each test provides a resolver that maps TS identifiers (e.g. `ThreadItem`, `Usage`, `TurnOptions`)
  to the matching Python symbol from the relevant `acodex.types.*` module(s).
- If the resolver returns `None`, the identifier is treated as external/unknown and is compatible
  with Python `object` shapes.

## Test coverage breakdown

### Exports

- TS: `vendor/codex-ts-sdk/src/index.ts`
- Python: `src/acodex/__init__.py` (`__all__`)
- Test: `tests/compatibility/test_sdk_exports.py`
  - Ensures all TS exports are present in Python.
  - Allows Python-only additions (`AsyncCodex`, `AsyncThread`) while still matching TS.

### Events (`events.ts`)

- TS: `vendor/codex-ts-sdk/src/events.ts`
- Python: `src/acodex/types/events.py`
- Test: `tests/compatibility/test_ts_events_compat.py`
  - Alias existence for each exported TS type alias.
  - Dataclass shape parity (fields and optionality).
  - Discriminator validation: `type` field default and `Literal[...]` annotation.
  - Type compatibility for each non-`type` field via `parse_ts_type_expr()` + `assert_ts_expr_compatible()`.
  - Cross-module reference checks for `Usage`, `ThreadItem`, `ThreadError`.

### Items (`items.ts`)

- TS: `vendor/codex-ts-sdk/src/items.ts`
- Python: `src/acodex/types/items.py`
- Test: `tests/compatibility/test_ts_items_compat.py`
  - String-literal unions parity (`CommandExecutionStatus`, etc.).
  - Dataclass shape parity (fields + discriminator).
  - Field type compatibility for each non-`type` field.
  - Inline object parsing parity for MCP result/error helper dataclasses.
  - External identifier tolerance (e.g. `McpContentBlock`).

### Options payloads

Codex options:
- TS: `vendor/codex-ts-sdk/src/codexOptions.ts`
- Python: `src/acodex/types/codex_options.py`
- Test: `tests/compatibility/test_ts_codex_options_compat.py`
  - Key set parity (camelCase -> snake_case).
  - Optionality parity (TS `?` -> Python `NotRequired[...]`).
  - Value type compatibility for each key.
  - Structural parity for recursive config types:
    - `CodexConfigValue` union membership expectations and `null` exclusion
    - `CodexConfigObject` index signature shape (`dict[str, CodexConfigValue]`)

Thread options:
- TS: `vendor/codex-ts-sdk/src/threadOptions.ts`
- Python: `src/acodex/types/thread_options.py`
- Test: `tests/compatibility/test_ts_thread_options_compat.py`
  - Literal unions parity: `ApprovalMode`, `SandboxMode`, `ModelReasoningEffort`, `WebSearchMode`
  - `ThreadOptions` key/optionality/value type parity

Turn options:
- TS: `vendor/codex-ts-sdk/src/turnOptions.ts`
- Python: `src/acodex/types/turn_options.py`
- Test: `tests/compatibility/test_ts_turn_options_compat.py`
  - `TurnOptions` key/optionality/value type parity (with `unknown` -> narrower accepted)
  - Explicit divergence assertion for cancellation primitive (`TurnSignal`)

### Thread types (`thread.ts`)

- TS: `vendor/codex-ts-sdk/src/thread.ts` (`Turn`, `UserInput`, `Input`)
- Python:
  - `src/acodex/types/turn.py` (`Turn`)
  - `src/acodex/types/input.py` (`UserInput*`, `Input`)
- Test: `tests/compatibility/test_ts_thread_types_compat.py`
  - `Turn` object type parity (TS-required subset):
    - `finalResponse` (TS) -> `final_response` (Python)
    - `Usage | null` (TS) -> `Usage | None` (Python)
    - Python-only `structured_response_factory` field is asserted as an intentional divergence
    - `structured_response` remains available as a property
  - `UserInput` union parity: variant dataclasses and discriminator literals
  - `Input` union parity: `string | UserInput[]` -> `str | list[UserInput]`

### Class surface (`codex.ts`, `thread.ts`)

- TS:
  - `vendor/codex-ts-sdk/src/codex.ts` (`Codex.startThread`, `Codex.resumeThread`)
  - `vendor/codex-ts-sdk/src/thread.ts` (`Thread.run`, `Thread.runStreamed`, `get id`)
- Python:
  - `src/acodex/codex.py` (`Codex`, `AsyncCodex`)
  - `src/acodex/thread.py` (`Thread`, `AsyncThread`)
- Test: `tests/compatibility/test_ts_class_surface_compat.py`
  - Method existence after camelCase -> snake_case mapping.
  - Getter existence (`id`) and return type hint (`str | None`).
  - Signature constraints (Python):
    - `start_thread`: no required args besides `self`
    - `resume_thread`: exactly one required positional `thread_id`
    - `run`/`run_streamed`: exactly one required positional `input`
    - optional Python-only `output_type` parameter exists on sync and async thread methods
  - Confirms Python is not async-only:
    - `Thread` provides sync methods
    - `AsyncThread` provides async methods (coroutine functions)

## Updating vendored TS SDK / handling contract changes

When the TS SDK changes in `vendor/codex-ts-sdk/src/`:

1. Run `make test`.
2. If compatibility tests fail:
   - Determine whether the TS change is intentional and should be reflected in Python.
   - Update Python types/classes to match TS contracts, or (rarely) add a documented divergence:
     - update `DIFFERENCES.md`
     - update/add a compatibility assertion for the divergence
3. Re-run gates:
   - `make format`
   - `make lint`
   - `make test`

## Extending compatibility coverage

If a new TS file/type is added to the public surface:

1. Ensure it is exported from `vendor/codex-ts-sdk/src/index.ts`.
2. Ensure Python exports the corresponding symbol from `src/acodex/__init__.py`.
3. Add a compatibility test in `tests/compatibility/` that:
   - Parses the TS alias/class from vendor sources
   - Resolves relevant Python symbols
   - Asserts key sets, discriminator literals, optionality, and type compatibility

If the TS type syntax goes beyond our parser subset, extend:
- `tools/compatibility/ts_type_expr.py` (preferred) or
- `tools/compatibility/ts_type_alias_parser.py` for alias extraction.

## Running the suite

Recommended order (mirrors repo quality gates):

1. `make format`
2. `make lint`
3. `make test`

Compatibility tests live in `tests/compatibility/` and are always executed as part of `make test`.
