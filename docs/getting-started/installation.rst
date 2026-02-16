Installation
============

Install prerequisites (Codex CLI) and then install the Python SDK.

When to use this page
---------------------

- You are installing acodex for the first time.
- You need to install or verify the Codex CLI prerequisite.
- You want the recommended uv-first install commands.

.. important::

   acodex is a community wrapper around the Codex CLI and is not affiliated with OpenAI.

Prerequisite: Codex CLI
-----------------------

acodex spawns an external executable named ``codex`` (or a custom path passed via
``codex_path_override``). You can install the upstream CLI with Node.js:

.. code-block:: bash

   npm install -g @openai/codex
   codex --version

See the upstream project for details: |codex_cli_repo|.

Install acodex
--------------

uv (recommended):

.. code-block:: bash

   uv add acodex

pip:

.. code-block:: bash

   pip install acodex

Optional: Structured-output extra for typed structured output
-------------------------------------------------------------

If you want ``output_type=...`` validation via Pydantic, install the extra:

.. code-block:: bash

   uv add "acodex[structured-output]"
   # or:
   pip install "acodex[structured-output]"
