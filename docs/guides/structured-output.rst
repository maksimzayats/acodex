Structured output
=================

Validate structured output into a typed Pydantic model via ``output_type`` (recommended), or
request schema-only structured output via ``output_schema`` (JSON Schema, TypeScript parity).

When to use this page
---------------------

- You want machine-readable outputs from the agent.
- You want typed validation (Pydantic) instead of ``dict`` parsing.

Typed validation (recommended: ``output_type``)
-----------------------------------------------

``output_type`` requires the optional Structured-output extra:

.. code-block:: bash

   uv add "acodex[structured-output]"
   # or:
   pip install "acodex[structured-output]"

.. code-block:: python

   from pydantic import BaseModel

   from acodex import Codex


   class SummaryPayload(BaseModel):
       summary: str


   turn = Codex().start_thread().run(
       "Summarize this repo.",
       output_type=SummaryPayload,
   )
   print(turn.structured_response.summary)

Schema-only parsing (TS parity: ``output_schema``)
--------------------------------------------------

.. code-block:: python

   from acodex import Codex

   schema = {
       "type": "object",
       "properties": {"summary": {"type": "string"}},
       "required": ["summary"],
       "additionalProperties": False,
   }

   turn = Codex().start_thread().run(
       "Summarize this repo.",
       output_schema=schema,
   )
   payload = turn.structured_response
   print(payload["summary"])

Error behavior
--------------

Structured parsing and validation are lazy and happen when ``turn.structured_response`` is
accessed. Failures raise ``acodex.exceptions.CodexStructuredResponseError``.
