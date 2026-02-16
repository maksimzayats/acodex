acodex
======

acodex is a typed Python SDK for the Codex CLI: run agent threads from Python (sync or async),
stream JSONL events as parsed dataclasses, request structured JSON output, and attach images as
inputs.

.. important::

   acodex is a community-maintained wrapper around the Codex CLI and is not affiliated with OpenAI.

Key features
------------

- **Typed surface**: strict type hints + mypy strict, no runtime dependencies by default.
- **Quality gates**: Ruff + mypy strict + 100% coverage.
- **Sync + async**: ``Codex`` / ``Thread`` and ``AsyncCodex`` / ``AsyncThread``.
- **Streaming events**: ``Thread.run_streamed()`` yields parsed ``ThreadEvent`` dataclasses.
- **Structured output**: ``output_type`` (Pydantic) or ``output_schema`` (JSON Schema, TS parity).
- **Images**: pass ``UserInputLocalImage`` alongside text in a single turn.
- **Resume threads**: ``resume_thread(thread_id)`` (threads persisted under ``~/.codex/sessions``).
- **Safety controls**: expose Codex CLI controls as ``ThreadOptions`` (``sandbox_mode``,
  ``approval_policy``, ``web_search_mode``, ``working_directory``, ...).
- **TS SDK parity**: the vendored TypeScript SDK is the source of truth; compatibility tests fail
  loudly on drift.

Quick links: |project_docs| - |project_repo| - |project_issues| - |codex_cli_repo|

Quickstart
----------

Install (uv):

.. code-block:: bash

   uv add acodex

.. code-block:: python

   from acodex import Codex

   thread = Codex().start_thread(
       sandbox_mode="read-only",
       approval_policy="on-request",
       web_search_mode="disabled",
   )
   turn = thread.run("Say hello")
   print(turn.final_response)

Next: :doc:`getting-started/quickstart` (structured output) and :doc:`guides/streaming` (events).

.. toctree::
   :maxdepth: 2
   :caption: Documentation

   getting-started/index
   guides/index
   compatibility/index
   reference/index
