# acodex

Typed Python SDK that wraps the `codex` CLI.

[![PyPI version](https://img.shields.io/pypi/v/acodex.svg)](https://pypi.org/project/acodex/)
[![Python versions](https://img.shields.io/pypi/pyversions/acodex.svg)](https://pypi.org/project/acodex/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![codecov](https://codecov.io/gh/maksimzayats/acodex/graph/badge.svg)](https://codecov.io/gh/maksimzayats/acodex)
[![Docs](https://img.shields.io/badge/docs-acodex.dev-blue)](https://docs.acodex.dev)

## What is acodex?

acodex is a typed Python SDK that spawns the `codex` CLI and exchanges JSONL events over
stdin/stdout. It provides both sync (`Codex`, `Thread`) and async (`AsyncCodex`, `AsyncThread`)
clients, exposes a streaming event API, and supports structured JSON output via JSON Schema.

## Why acodex

- Fully typed public API (mypy-friendly).
- Sync and async client surfaces.
- Stream parsed `ThreadEvent` objects via `run_streamed()`.
- Completed turns include `turn.final_response`, `turn.structured_response`, `turn.items`, and
  `turn.usage`.
- Attach local images (`UserInputLocalImage`) with stable input normalization for text.
- Request structured JSON output via `output_schema`.
- Resume conversations with `resume_thread()` (threads persisted under `~/.codex/sessions`).
- Cancellation via `threading.Event` / `asyncio.Event` (`TurnOptions.signal`).

## Installation (uv)

### Prerequisites: Codex CLI

acodex wraps an external CLI. Ensure `codex` is installed and available on `PATH` (or pass
`codex_path_override=...` when constructing the client).

One installation option (requires Node.js >=16):

```bash
npm install -g @openai/codex
codex --version
```

### Install acodex

```bash
uv add acodex
```

Run a script using the project environment:

```bash
uv run python your_script.py
```

`pip install acodex` also works, but `uv` is recommended.

## Quickstart (sync)

```python
from acodex import Codex

codex = Codex()
thread = codex.start_thread()

schema = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}

turn = thread.run(
    'Summarize repository health. Return JSON: {"summary": "..."}',
    output_schema=schema,
)
print(turn.structured_response["summary"])
print(turn.items)
```

Call `run()` repeatedly on the same `Thread` instance to continue the conversation.

## Streaming events

Use `run_streamed()` to react to intermediate progress (tool calls, streaming responses, item
updates, and final usage).

```python
from acodex import Codex, ItemCompletedEvent, TurnCompletedEvent, TurnFailedEvent

codex = Codex()
thread = codex.start_thread()
schema = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}

streamed = thread.run_streamed(
    'Summarize implementation status. Return JSON: {"summary": "..."}',
    output_schema=schema,
)
for event in streamed.events:
    if isinstance(event, ItemCompletedEvent):
        print("item", event.item)
    elif isinstance(event, TurnCompletedEvent):
        print("usage", event.usage)
    elif isinstance(event, TurnFailedEvent):
        print("error", event.error.message)

turn = streamed.result
print(turn.structured_response["summary"])
```

`streamed.result` is available only after `streamed.events` is fully consumed.

## Structured output (`output_schema` + `output_type`)

`turn.structured_response` behaves in three modes:

- no `output_schema` and no `output_type`: accessing `turn.structured_response` raises
  `CodexStructuredResponseError`
- `output_schema` only: accessing `turn.structured_response` parses JSON
  (`json.loads(final_response)`)
- `output_type` provided: accessing `turn.structured_response` validates JSON with Pydantic and
  returns typed data

Structured parsing and validation are lazy and happen only when `turn.structured_response` is
accessed.

When both are missing, the error message is:
`No output schema available for validating structured response. Provide an \`output_type\` or \`output_schema\` to enable validation.`

Schema-only parsing:

```python
from acodex import Codex

schema = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}

turn = Codex().start_thread().run("Summarize repository status", output_schema=schema)
print(turn.structured_response["summary"])
```

Typed validation with `output_type`:

`output_type` requires the optional Pydantic extra:

```bash
pip install "acodex[pydantic]"
```

```python
from pydantic import BaseModel

from acodex import Codex


class SummaryPayload(BaseModel):
    summary: str


turn = Codex().start_thread().run("Summarize repository status", output_type=SummaryPayload)
print(turn.structured_response.summary)
```

`CodexStructuredResponseError` is raised when structured parsing or validation fails:

- missing both `output_schema` and `output_type`
- invalid JSON for `output_schema`-only runs
- payload that does not match `output_type`

## Images in prompts

Provide structured input entries when you need to include images alongside text.

```python
from acodex import Codex
from acodex.types.input import UserInputLocalImage, UserInputText

thread = Codex().start_thread()
schema = {
    "type": "object",
    "properties": {"description": {"type": "string"}},
    "required": ["description"],
    "additionalProperties": False,
}
turn = thread.run(
    [
        UserInputText(text='Describe this image. Return JSON: {"description": "..."}'),
        UserInputLocalImage(path="./ui.png"),
    ],
    output_schema=schema,
)
print(turn.structured_response["description"])
```

## Async (brief)

```python
import asyncio

from acodex import AsyncCodex


async def main() -> None:
    thread = AsyncCodex().start_thread()
    schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }
    turn = await thread.run(
        'Say hello from async. Return JSON: {"message": "..."}',
        output_schema=schema,
    )
    print(turn.structured_response["message"])


asyncio.run(main())
```

## Configuration notes

- Client options: `Codex(codex_path_override=..., env=..., config=..., api_key=..., base_url=...)`
- Thread options: `start_thread(working_directory=..., sandbox_mode=..., approval_policy=..., web_search_mode=...)`

## Links

- GitHub: https://github.com/maksimzayats/acodex
- Issues: https://github.com/maksimzayats/acodex/issues
- Docs: https://docs.acodex.dev
- Differences from TS SDK: `DIFFERENCES.md`

## License

Apache-2.0. See `LICENSE`.
