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
- Completed turns include `turn.final_response`, `turn.items`, and `turn.usage`.
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

turn = thread.run("Diagnose the test failure and propose a fix")
print(turn.final_response)
print(turn.items)
```

Call `run()` repeatedly on the same `Thread` instance to continue the conversation.

## Streaming events

Use `run_streamed()` to react to intermediate progress (tool calls, streaming responses, item
updates, and final usage).

```python
from acodex import Codex

codex = Codex()
thread = codex.start_thread()

streamed = thread.run_streamed("Implement the fix")
for event in streamed.events:
    if event.type == "item.completed":
        print("item", event.item)
    elif event.type == "turn.completed":
        print("usage", event.usage)
    elif event.type == "turn.failed":
        print("error", event.error.message)

turn = streamed.result
print(turn.final_response)
```

`streamed.result` is available only after `streamed.events` is fully consumed.

## Structured output (JSON schema)

Provide a JSON Schema per turn via `output_schema`. The agent returns a JSON response string in
`turn.final_response`.

```python
import json

from acodex import Codex

schema = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "status": {"type": "string", "enum": ["ok", "action_required"]},
    },
    "required": ["summary", "status"],
    "additionalProperties": False,
}

turn = Codex().start_thread().run("Summarize repository status", output_schema=schema)
payload = json.loads(turn.final_response)
print(payload["summary"], payload["status"])
```

## Images in prompts

Provide structured input entries when you need to include images alongside text.

```python
from acodex import Codex
from acodex.types.input import UserInputLocalImage, UserInputText

thread = Codex().start_thread()
turn = thread.run(
    [
        UserInputText(text="Describe this image"),
        UserInputLocalImage(path="./ui.png"),
    ],
)
print(turn.final_response)
```

## Async (brief)

```python
import asyncio

from acodex import AsyncCodex


async def main() -> None:
    thread = AsyncCodex().start_thread()
    turn = await thread.run("Hello from async")
    print(turn.final_response)


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
