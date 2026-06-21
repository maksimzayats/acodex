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
- Keep production code WPS-clean without production per-file ignores. Plain
  service classes should be slotted; Pydantic models/settings and exceptions are
  the main slotscheck exceptions.
- Exclude `references/` and `tmp/` from lint, type, spelling, package, and test
  assumptions. They are local references only.
- Update tests and docs with behavior changes. Keep user-facing content in
  `README.md`, contributor workflow in `CONTRIBUTING.md`, and agent-only rules
  in this file.
