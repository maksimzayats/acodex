Threads and sessions
====================

Threads represent a conversation with the agent. Codex persists thread sessions on disk so you can
resume a conversation later by ID.

When to use this page
---------------------

- You want to keep context across multiple turns.
- You want to resume a thread across processes or machines.

Start a thread
--------------

.. code-block:: python

   from acodex import Codex

   thread = Codex().start_thread()
   turn = thread.run("Hello")
   print("thread id:", thread.id)

``thread.id`` is populated after the first turn starts.

Resume a thread
---------------

Threads are persisted under ``~/.codex/sessions`` by the Codex CLI.

.. code-block:: python

   from acodex import Codex

   client = Codex()
   thread = client.resume_thread("thread_123")
   turn = thread.run("Continue from where we left off.")
   print(turn.final_response)
