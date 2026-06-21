# Agent Instructions

- Keep new features split by responsibility: CLI presentation in `cli`, HTTP
  transport in `http`, Codex desktop bridging in `core/codex_app`, MCP client
  logic in `core/mcp_tools.py`, and dependency wiring in `ioc`.
- Use dependency injection for shared services and I/O boundaries. Register
  reusable collaborators in the container instead of constructing them ad hoc.
- Keep dependency wiring behind process entrypoints. Do not import `ioc` from
  feature modules, and do not make `cli`, `http`, or `core` depend on each other
  across the enforced import-linter boundaries.
- Prefer focused classes or dataclasses for main feature logic, especially when
  dependencies, state, lifecycle, or test seams are involved. Keep standalone
  functions for small pure helpers and simple transformations.
- Keep package `__init__.py` files as public facades only. Do not add private
  backward-compatibility wrappers, `compat.py` shims, or aliases just for old
  tests; update tests and callers to use the real class/module API instead.
- Keep production code WPS-clean without production per-file ignores. Plain
  service classes should be slotted; Pydantic models/settings and exceptions are
  the main slotscheck exceptions.
- Treat Ruff, WPS/Flake8, mypy, import-linter, pyright, pyrefly, slotscheck,
  pytest with 100% coverage, and `prek run --all-files` as required gates.
  Preserve these gates when changing tooling.
- Exclude `references/` and `tmp/` from lint, type, spelling, package, and test
  assumptions. They are local references only.
- Update tests and docs with behavior changes. Keep user-facing content in
  `README.md`, contributor workflow in `CONTRIBUTING.md`, and agent-only rules
  in this file.
