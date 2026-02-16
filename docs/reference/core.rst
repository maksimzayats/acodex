Core API
========

Primary client and thread classes.

When to use this page
---------------------

- You want docstrings for the main entry points: ``Codex``, ``Thread``, and async equivalents.
- You want the exact ``run`` / ``run_streamed`` signatures and return types.

.. automodule:: acodex.codex
   :members: Codex, AsyncCodex
   :member-order: bysource

.. automodule:: acodex.thread
   :members: Thread, AsyncThread
   :member-order: bysource

.. automodule:: acodex.types.turn
   :members: RunResult, RunStreamedResult, AsyncRunStreamedResult, Turn
   :member-order: bysource
