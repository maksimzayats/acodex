Safety, sandboxing, and approvals
=================================

acodex forwards thread-level safety controls to the Codex CLI via ``ThreadOptions`` so callers can
choose appropriate defaults for their environment.

When to use this page
---------------------

- You need to restrict filesystem/network access for tool execution.
- You want explicit approval prompts for commands and tool calls.
- You want to control web search behavior.

Thread-level controls
---------------------

Thread options are passed to ``Codex.start_thread(...)`` / ``Codex.resume_thread(...)`` (and async
equivalents). They apply to every turn in that thread:

.. code-block:: python

   from acodex import Codex

   thread = Codex().start_thread(
       sandbox_mode="read-only",
       approval_policy="on-request",
       web_search_mode="disabled",
       working_directory=".",
   )

Common options you may want to set:

- ``sandbox_mode``: execution sandbox profile (for example, ``"read-only"``).
- ``approval_policy``: when tools/commands require explicit approval (for example, ``"on-request"``).
- ``web_search_mode``: configure if/how web search is used (for example, ``"disabled"``).
- ``working_directory``: the working directory the CLI uses for the turn.
- ``additional_directories``: extra directories to include in the execution workspace.

Turn-level controls
-------------------

Turn options are passed to ``Thread.run(...)`` / ``Thread.run_streamed(...)``:

- ``signal`` (``threading.Event`` or ``asyncio.Event``): set the event to request cancellation.
- ``output_schema``: request structured JSON output for that turn.

Notes
-----

- acodex does not implement its own sandbox; it forwards configuration to the Codex CLI.
- Choose defaults that fit your risk tolerance and environment.
