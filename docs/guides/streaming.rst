Streaming events
================

Stream parsed events from the Codex CLI as a turn runs so you can react to intermediate progress
(items, usage, and errors).

When to use this page
---------------------

- You want incremental updates while the agent is working.
- You want to capture tool calls / file changes / to-do list items as they complete.

Sync streaming
--------------

.. code-block:: python

   from acodex import (
       Codex,
       ItemCompletedEvent,
       ItemStartedEvent,
       ThreadErrorEvent,
       TurnCompletedEvent,
       TurnFailedEvent,
   )

   thread = Codex().start_thread()
   streamed = thread.run_streamed("Refactor this module and explain the changes.")

   for event in streamed.events:
       if isinstance(event, ItemStartedEvent):
           print("started:", event.item.type)
       elif isinstance(event, ItemCompletedEvent):
           print("completed:", event.item.type)
       elif isinstance(event, TurnCompletedEvent):
           print("usage:", event.usage)
       elif isinstance(event, TurnFailedEvent):
           print("turn failed:", event.error.message)
       elif isinstance(event, ThreadErrorEvent):
           print("stream error:", event.message)

   turn = streamed.result
   print(turn.final_response)

``streamed.result`` is only available after ``streamed.events`` is fully consumed.

Async streaming
---------------

.. code-block:: python

   import asyncio

   from acodex import (
       AsyncCodex,
       ItemCompletedEvent,
       TurnCompletedEvent,
   )


   async def main() -> None:
       thread = AsyncCodex().start_thread()
       streamed = await thread.run_streamed("List 3 options for a migration plan.")

       async for event in streamed.events:
           if isinstance(event, ItemCompletedEvent):
               print("completed:", event.item.type)
           elif isinstance(event, TurnCompletedEvent):
               print("usage:", event.usage)

       print(streamed.result.final_response)


   asyncio.run(main())
