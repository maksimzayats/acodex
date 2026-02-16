Compatibility
=============

acodex vendors the upstream TypeScript SDK and treats it as the source of truth for the public
surface. CI enforces parity by parsing the vendored TS sources and checking the Python surface.

When to use this section
------------------------

- You want confidence that Python stays aligned with upstream releases.
- You are bumping the vendored SDK and need to fix compatibility failures.

.. toctree::
   :maxdepth: 2

   parity-and-automation
   differences
