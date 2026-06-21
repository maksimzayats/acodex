# Agent Instructions

- Keep new features split by responsibility: CLI presentation in `cli`, HTTP
  transport in `http`, Codex desktop bridging in `core/codex_app`, MCP client
  logic in `core/mcp_tools.py`, and dependency wiring in `ioc`.
- Use dependency injection for shared services and I/O boundaries. Register
  reusable collaborators in the container instead of constructing them ad hoc.
- Prefer focused classes or dataclasses for main feature logic, especially when
  dependencies, state, lifecycle, or test seams are involved. Keep standalone
  functions for small pure helpers and simple transformations.
- Update tests and docs with behavior changes. Keep user-facing content in
  `README.md`, contributor workflow in `CONTRIBUTING.md`, and agent-only rules
  in this file.
