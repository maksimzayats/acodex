Quickstart
==========

Start a thread, run a turn, and read the final response (optionally as JSON).

When to use this page
---------------------

- You want the smallest working example.
- You want to confirm structured output end-to-end.

Sync client
-----------

This example uses typed structured output via a Pydantic model (``output_type``). Install the
optional extra first: ``uv add "acodex[pydantic]"``.

.. code-block:: python

   from pydantic import BaseModel

   from acodex import Codex

   class SummaryPayload(BaseModel):
       summary: str

   thread = Codex().start_thread(
       sandbox_mode="read-only",
       approval_policy="on-request",
       web_search_mode="disabled",
   )
   turn = thread.run("Summarize this repo.", output_type=SummaryPayload)
   print(turn.structured_response.summary)

Async client
------------

.. code-block:: python

   import asyncio

   from acodex import AsyncCodex


   async def main() -> None:
       thread = AsyncCodex().start_thread()
       turn = await thread.run("Say hello")
       print(turn.final_response)


   asyncio.run(main())
