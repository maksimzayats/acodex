Parity and automation
=====================

How acodex keeps its Python surface compatible with the vendored TypeScript SDK, and how the
automation bumps the vendor when upstream releases.

What this means for you
-----------------------

- You can treat the TypeScript SDK as the canonical reference and expect the same concepts and
  option keys in Python (with snake_case naming).
- Upstream changes show up quickly as failing compatibility tests instead of silent drift.
- Intentional Python differences are explicitly documented and asserted in CI.

When to use this page
---------------------

- You want confidence that Python matches the upstream SDK.
- You are updating the vendored TypeScript SDK and need to fix drift.

Source of truth
---------------

- Vendored SDK: ``vendor/codex-ts-sdk/src/``
- TS export index: ``vendor/codex-ts-sdk/src/index.ts``
- Python exports: ``src/acodex/__init__.py``
- Compatibility suite: ``tests/compatibility/``

Automation
----------

The upstream release bump is automated via an hourly workflow:

- Workflow: ``.github/workflows/codex-ts-sdk-bump.yaml``
- Schedule: hourly (``cron: "0 * * * *"``)
- Output: opens a PR on branch ``codex/bump-ts-sdk`` when a new stable release is available

Local workflow
--------------

Vendor the latest stable release:

.. code-block:: bash

   make vendor-ts-sdk-latest

Run the compatibility suite:

.. code-block:: bash

   uv run pytest tests/compatibility/

If you intentionally add a Python-specific deviation, document it in ``DIFFERENCES.md`` and add a
compatibility assertion so the divergence is explicit and stable.
