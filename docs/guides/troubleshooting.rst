Troubleshooting
===============

Common issues and how to resolve them.

When to use this page
---------------------

- You get an exception from acodex and want the next step.
- The Codex CLI executable is not found or fails to run.
- Structured output parsing/validation fails.

Executable not found
--------------------

If you see ``CodexExecutableNotFoundError``:

- Ensure the Codex CLI is installed and ``codex`` is on ``PATH``.
- Or pass ``codex_path_override="/path/to/codex"`` to ``Codex(...)`` / ``AsyncCodex(...)``.

Structured output errors
------------------------

If you see ``CodexStructuredResponseError`` when accessing ``turn.structured_response``:

- Ensure your prompt actually returns JSON matching the schema/model.
- If using ``output_type``, ensure you installed the extra: ``uv add "acodex[pydantic]"`` (or
  ``pip install "acodex[pydantic]"``).

Streamed result accessed too early
----------------------------------

If you see ``CodexThreadStreamNotConsumedError``:

- Consume the full ``streamed.events`` iterator (or async iterator) before accessing
  ``streamed.result``.
