# acodex

A typed Python SDK for the Codex CLI (sync + async, streaming events, structured output, images).

acodex is a community-maintained wrapper around the Codex CLI and is not affiliated with OpenAI.

[![PyPI version](https://img.shields.io/pypi/v/acodex.svg)](https://pypi.org/project/acodex/)
[![Python versions](https://img.shields.io/pypi/pyversions/acodex.svg)](https://pypi.org/project/acodex/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![codecov](https://codecov.io/gh/maksimzayats/acodex/graph/badge.svg)](https://codecov.io/gh/maksimzayats/acodex)
[![Docs](https://img.shields.io/badge/docs-acodex.dev-blue)](https://docs.acodex.dev)

## What is acodex?

acodex spawns the `codex` CLI and exchanges JSONL events over stdin/stdout so you can run agent
threads from Python with a fully typed surface: sync + async clients, streaming events, structured
output, image inputs, resumable threads, and safety controls exposed as explicit options.

## Install

### Prerequisite: Codex CLI

acodex wraps an external CLI. Install the Codex CLI and ensure `codex` is on your `PATH` (or pass
`codex_path_override=...` to `Codex(...)` / `AsyncCodex(...)`).

- Upstream CLI: https://github.com/openai/codex

One installation option:

```bash
npm install -g @openai/codex
codex --version
```

### Install acodex (uv-first)

```bash
uv add acodex
uv run python your_script.py
```

`pip install acodex` also works, but `uv` is recommended.

Recommended for structured output: Pydantic extra (primary pattern via `output_type`):

```bash
uv add "acodex[pydantic]"
# or:
pip install "acodex[pydantic]"
```

## 60-second quickstart (sync)

```python
from pydantic import BaseModel

from acodex import Codex

class SummaryPayload(BaseModel):
    summary: str

thread = Codex().start_thread(
    sandbox_mode="read-only",
    approval_policy="on-request",
    web_search_mode="disabled",
)
turn = thread.run(
    "Summarize this repo.",
    output_type=SummaryPayload,
)
print(turn.structured_response.summary)
```

Call `run()` repeatedly on the same `Thread` instance to continue the conversation. To resume later
from disk, use `Codex().resume_thread(thread_id)`.

## Async quickstart

```python
import asyncio

from acodex import AsyncCodex


async def main() -> None:
    thread = AsyncCodex().start_thread()
    turn = await thread.run("Say hello")
    print(turn.final_response)


asyncio.run(main())
```

## Advanced: stream parsed events

Use `run_streamed()` to react to intermediate progress (tool calls, streaming responses, item
updates, and final usage).

```python
from acodex import Codex, ItemCompletedEvent, TurnCompletedEvent, TurnFailedEvent

codex = Codex()
thread = codex.start_thread()

streamed = thread.run_streamed(
    "List the top 3 risks for this codebase. Be concise.",
)
for event in streamed.events:
    if isinstance(event, ItemCompletedEvent):
        print("item", event.item)
    elif isinstance(event, TurnCompletedEvent):
        print("usage", event.usage)
    elif isinstance(event, TurnFailedEvent):
        print("error", event.error.message)

turn = streamed.result
print(turn.final_response)
```

`streamed.result` is available only after `streamed.events` is fully consumed.

## Why acodex

- **Typed surface**: strict type hints + mypy strict, no runtime deps by default.
- **Sync + async**: `Codex`/`Thread` and `AsyncCodex`/`AsyncThread`.
- **Streaming events**: `Thread.run_streamed()` yields parsed `ThreadEvent` dataclasses.
- **Structured output**: validate into a Pydantic model via `output_type` (recommended), or pass
  `output_schema` (JSON Schema) for schema-only parity with the TypeScript SDK.
- **Images**: pass `UserInputLocalImage` alongside text in a single turn.
- **Resume threads**: `resume_thread(thread_id)` (threads persisted under `~/.codex/sessions`).
- **Safety controls**: expose Codex CLI controls as `ThreadOptions` (`sandbox_mode`,
  `approval_policy`, `web_search_mode`, `working_directory`, ...).
- **TS SDK parity**: vendored TypeScript SDK is the source of truth; compatibility tests fail loudly
  on drift.
- **Quality gates**: Ruff + mypy strict + 100% coverage.

## Compatibility & parity (TypeScript SDK)

The vendored TypeScript SDK under `vendor/codex-ts-sdk/src/` is the source of truth. CI runs a
Python-only compatibility suite that parses those TS sources and asserts the Python exports,
options keys, events/items models, and class surface stay compatible.

An hourly workflow checks for new stable Codex releases and opens a PR to bump the vendored SDK:
`.github/workflows/codex-ts-sdk-bump.yaml`.

- Compatibility policy: `COMPATIBILITY.md`
- Intentional divergences (documented + tested): `DIFFERENCES.md`
- Contributing: `CONTRIBUTING.md`

## Links

- Docs: https://docs.acodex.dev
- GitHub: https://github.com/maksimzayats/acodex
- Issues: https://github.com/maksimzayats/acodex/issues

## License

Apache-2.0. See `LICENSE`.
