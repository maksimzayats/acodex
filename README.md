# acodex

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Local MCP automation for the Codex desktop app.**

acodex gives scripts, tools, and agents a local bridge into a running Codex
desktop session. It can relaunch Codex with a Chrome DevTools Protocol (CDP)
port, run a managed HTTP/MCP server, and call the live `codex_app.*` tools that
your Codex desktop build exposes.

[Quick Start](#quick-start) | [CLI](#cli) | [Support](#support) | [Contributing](CONTRIBUTING.md)

## Why acodex

- **Live Codex desktop access.** Inspect and call the tools exposed by the
  running desktop renderer without writing CDP plumbing.
- **MCP-compatible local server.** Expose Codex desktop tools at `/mcp` for
  local automation clients.
- **Practical CLI workflow.** Check configuration, relaunch Codex with CDP,
  manage the bridge server, and call tools from a terminal.

## Quick Start

Prerequisites:

- Python 3.10 or newer.
- `uv`; see the [official install guide](https://docs.astral.sh/uv/getting-started/installation/).
- macOS with Codex.app installed. The relaunch flow expects
  `/Applications/Codex.app` by default; set `ACODEX_CODEX_APP_PATH` if yours is
  elsewhere.

Install the CLI:

```sh
uv tool install acodex
```

Initialize config, launch Codex with CDP, and start the local bridge:

```sh
acodex config init
acodex codex relaunch --yes
acodex server start
```

`acodex codex relaunch --yes` starts or restarts Codex so acodex can reach the
default CDP endpoint, `http://127.0.0.1:45217`.

For deeper diagnostics after the server is running, use `acodex doctor --deep`.

List and call Codex desktop tools:

```sh
acodex tools list
acodex tools call codex_app.list_threads --limit 1
```

Stop the managed bridge when you are done:

```sh
acodex server stop
```

## CLI

Common commands:

```sh
acodex config path
acodex config show
acodex doctor --deep
acodex codex status
acodex codex relaunch --yes
acodex server start
acodex server status
acodex server logs --tail 50
acodex tools list --json
acodex tools call codex_app.list_threads --help
```

Tool calls use the MCP schema property names. Pass simple top-level arguments as
flags, or use JSON for nested input:

```sh
acodex tools call codex_app.list_threads --limit=5
acodex tools call --args-json '{"limit":5}' codex_app.list_threads
acodex tools call --output json codex_app.list_threads --limit 5
```

## Configuration

acodex reads JSON config from `~/.acodex/config.json` by default. Set
`ACODEX_CONFIG` to use a different file. Use `acodex config path` and
`acodex config show` to inspect the active path and effective values.

Essential local endpoints:

- Codex CDP: `http://127.0.0.1:45217`
- Managed server health: `http://127.0.0.1:45218/healthz`
- MCP endpoint: `http://127.0.0.1:45218/mcp`

Configuration precedence and the full defaults matrix live in
[CONTRIBUTING.md](CONTRIBUTING.md).

State-changing tool calls mutate the live Codex desktop app. Use
`acodex tools call <tool> --help` before calling unfamiliar tools.

## Support

When setup fails, start with the built-in diagnostics and managed server logs:

```sh
acodex doctor
acodex server logs --tail 50
```

If the issue continues, open a
[GitHub issue](https://github.com/maksimzayats/acodex/issues) with what you
tried, what happened, your OS and Python version, your acodex source branch or
commit, your Codex desktop/CDP setup, and relevant command output with secrets
removed.

## Contributing

Contributor setup, architecture notes, quality gates, and documentation rules
live in [CONTRIBUTING.md](CONTRIBUTING.md). Agent-specific guidance lives in
[AGENTS.md](AGENTS.md).

## License

acodex is released under the [MIT License](LICENSE).

acodex is independently maintained and is not affiliated with, sponsored by, or
endorsed by OpenAI.
