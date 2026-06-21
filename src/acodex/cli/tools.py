from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from diwire import Injected
from rich import box
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from acodex.cli.server import ServerError, ServerManager
from acodex.core.mcp_tools import MCPToolsClient

_ARGUMENT_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_MCP_TOOL_RESULT_SHAPE = {
    "content": [{"type": "text", "text": "..."}],
    "isError": False,
}
_KNOWN_TOOL_OUTPUT_SHAPES: dict[str, dict[str, Any]] = {
    "codex_app.list_threads": {
        "schemaVersion": 1,
        "query": "string | null",
        "threads": [
            {
                "id": "string",
                "hostId": "string",
                "title": "string",
                "preview": "string",
                "status": "string",
                "cwd": "string | null",
                "createdAt": "number",
                "updatedAt": "number",
            },
        ],
    },
}


def _build_server_manager() -> ServerManager:
    return ServerManager()


class ToolOutput(str, Enum):
    text = "text"
    json = "json"


class ToolArgumentsError(ValueError):
    """Raised when tool arguments cannot be parsed from CLI tokens."""


@dataclass(frozen=True, slots=True)
class ToolArgumentsParser:
    @staticmethod
    def parse(
        tokens: list[str],
        *,
        args_json: str | None = None,
        args_json_file: Path | None = None,
    ) -> dict[str, Any]:
        """Parse CLI tokens and optional JSON sources into a tool arguments object.

        Returns:
            Parsed JSON-compatible tool arguments.

        Raises:
            ToolArgumentsError: If the CLI tokens or JSON sources are invalid.

        """
        arguments = _load_json_arguments(args_json=args_json, args_json_file=args_json_file)
        token_arguments = _parse_option_tokens(tokens)

        duplicates = sorted(set(arguments).intersection(token_arguments))
        if duplicates:
            joined = ", ".join(duplicates)
            raise ToolArgumentsError(f"Duplicate tool argument: {joined}")

        return {**arguments, **token_arguments}

    @staticmethod
    def is_help_request(tokens: list[str]) -> bool:
        """Return whether the dynamic tool arguments request tool help.

        Returns:
            True when `--help` appears after the tool name.

        """
        return "--help" in tokens


@dataclass(frozen=True, slots=True)
class MCPToolsClientFactory:
    @staticmethod
    def create(*, mcp_url: str) -> MCPToolsClient:
        """Build an MCP tools client for the managed server URL.

        Returns:
            Configured MCP tools client.

        """
        return MCPToolsClient(mcp_url=mcp_url)


@dataclass(frozen=True, kw_only=True, slots=True)
class ManagedMCPToolsClientProvider:
    server_manager: Injected[ServerManager]
    client_factory: Injected[MCPToolsClientFactory]

    def create(self) -> MCPToolsClient:
        """Return an MCP tools client after validating managed server status.

        Returns:
            MCP tools client for the managed server.

        Raises:
            ServerError: If the managed server is stopped, unhealthy, or missing an MCP URL.

        """
        status = self.server_manager.status()
        if not status.get("running"):
            raise ServerError("Managed server is not running. Start it with `acodex server start`.")
        if not status.get("healthy"):
            raise ServerError(
                "Managed server is not healthy. Check `acodex server logs --tail 50` or restart it.",
            )

        mcp_url = status.get("mcp_url")
        if not isinstance(mcp_url, str) or not mcp_url:
            raise ServerError("Managed server status did not include an MCP URL. Restart it.")
        return self.client_factory.create(mcp_url=mcp_url)


@dataclass(kw_only=True, slots=True)
class ToolsPresenter:
    console: Console = field(default_factory=Console)

    def json(self, payload: Any) -> None:
        """Print a payload as formatted JSON."""
        self.console.print_json(json.dumps(payload, indent=2))

    def tools_list(self, tools: list[dict[str, Any]]) -> None:
        """Print the human-readable tools list."""
        if not tools:
            self.warning("No tools are currently exposed")
            return

        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Description", overflow="fold")
        for tool in tools:
            table.add_row(str(tool.get("name", "")), str(tool.get("description", "")))
        self.console.print(panel("Codex Tools", table))

    def tool_help(self, *, name: str, tools: list[dict[str, Any]]) -> None:
        """Print help for a single MCP tool descriptor.

        Raises:
            ValueError: If the requested tool is not present in the tool descriptors.

        """
        descriptor = find_tool_descriptor(tools, name)
        if descriptor is None:
            raise ValueError(f"Tool not found: {name}")

        summary = Table.grid(expand=True, padding=(0, 2))
        summary.add_column(style="bold", no_wrap=True)
        summary.add_column(ratio=1, overflow="fold")
        summary.add_row("Name", str(descriptor.get("name", name)))
        summary.add_row("Description", str(descriptor.get("description", "")))
        summary.add_row("Usage", f"acodex tools call {name} --argument value")

        self.console.print(panel("Tool Help", summary))
        self.console.print(panel("Input schema", json_syntax(descriptor.get("inputSchema", {}))))
        output_shape = tool_output_shape(descriptor)
        if output_shape is not None:
            self.console.print(panel("Default output payload shape", json_syntax(output_shape)))
        else:
            self.console.print(panel("Default output", tool_output_note()))
        self.console.print(
            panel("Raw MCP result (--output json)", json_syntax(_MCP_TOOL_RESULT_SHAPE)),
        )

    def tool_call_result(self, result: dict[str, Any], *, output: ToolOutput) -> None:
        """Print a tool call result in the requested output format."""
        if output == ToolOutput.json:
            self.json(result)
            return

        text = tool_result_text(result)
        if text:
            self.console.print(text, markup=False, highlight=False, soft_wrap=True)

    def warning(self, message: str, detail: str | None = None) -> None:
        """Print a warning message."""
        text = Text(message, style="bold yellow")
        if detail is not None:
            text.append(f"\n{detail}", style="cyan")
        self.console.print(text)


@dataclass(frozen=True, kw_only=True, slots=True)
class ToolsCommand:
    client_provider: Injected[ManagedMCPToolsClientProvider]
    parser: Injected[ToolArgumentsParser]
    presenter: Injected[ToolsPresenter]

    def list_tools(self, *, json_output: bool) -> None:
        """List available MCP tools and render them for the CLI."""
        tools = self.client_provider.create().list_tools()
        if json_output:
            self.presenter.json({"tools": tools})
            return
        self.presenter.tools_list(tools)

    def call(
        self,
        *,
        name: str,
        raw_args: list[str],
        output: ToolOutput,
        args_json: str | None,
        args_json_file: Path | None,
    ) -> int:
        """Call a single MCP tool or render its help.

        Returns:
            Process exit code for the tool call.

        """
        client = self.client_provider.create()
        if self.parser.is_help_request(raw_args):
            self.presenter.tool_help(name=name, tools=client.list_tools())
            return 0

        arguments = self.parser.parse(
            raw_args,
            args_json=args_json,
            args_json_file=args_json_file,
        )
        result = client.call_tool(name, arguments)
        self.presenter.tool_call_result(result, output=output)
        return 1 if result.get("isError") is True else 0


def parse_tool_arguments(
    tokens: list[str],
    *,
    args_json: str | None = None,
    args_json_file: Path | None = None,
) -> dict[str, Any]:
    return ToolArgumentsParser().parse(tokens, args_json=args_json, args_json_file=args_json_file)


def find_tool_descriptor(tools: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    normalized = name.replace("codex_app__", "codex_app.", 1)
    bare = normalized.removeprefix("codex_app.")
    candidates = {normalized, f"codex_app.{bare}"}
    for tool in tools:
        if tool.get("name") in candidates:
            return tool
    return None


def json_syntax(payload: Any) -> Syntax:
    return Syntax(json.dumps(payload, indent=2, ensure_ascii=False), "json", word_wrap=True)


def tool_output_shape(descriptor: dict[str, Any]) -> dict[str, Any] | None:
    output_schema = descriptor.get("outputSchema")
    if isinstance(output_schema, dict):
        return output_schema
    name = descriptor.get("name")
    if isinstance(name, str):
        return _KNOWN_TOOL_OUTPUT_SHAPES.get(name)
    return None


def tool_output_note() -> Text:
    return Text(
        "This tool descriptor does not declare an output schema. "
        "Default output prints text content from the MCP result; use --output json for the raw wrapper.",
    )


def tool_result_text(result: dict[str, Any]) -> str:
    content = result.get("content")
    if not isinstance(content, list):
        return json.dumps(result, ensure_ascii=False)

    lines: list[str] = []
    for item in content:
        if (
            isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        ):
            lines.append(item["text"])
        else:
            lines.append(json.dumps(item, ensure_ascii=False))
    return "\n".join(lines)


def panel(title: str, renderable: RenderableType) -> Panel:
    return Panel(
        renderable,
        title=title,
        title_align="left",
        box=box.ROUNDED,
        border_style="dim",
        padding=(0, 1),
    )


def _load_json_arguments(
    *,
    args_json: str | None,
    args_json_file: Path | None,
) -> dict[str, Any]:
    if args_json is not None and args_json_file is not None:
        raise ToolArgumentsError("--args-json and --args-json-file cannot be used together")
    if args_json is None and args_json_file is None:
        return {}
    if args_json_file is not None:
        try:
            return _json_object(
                args_json_file.read_text(encoding="utf-8"),
                source=str(args_json_file),
            )
        except OSError as exc:
            raise ToolArgumentsError(
                f"Could not read tool arguments from {args_json_file}: {exc}",
            ) from exc
    return _json_object(args_json or "", source="--args-json")


def _json_object(raw_json: str, *, source: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ToolArgumentsError(f"{source} must contain valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ToolArgumentsError(f"{source} must contain a JSON object")
    return payload


def _parse_option_tokens(tokens: list[str]) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        raw_argument = tokens[index]
        if not raw_argument.startswith("--") or raw_argument == "--":
            raise ToolArgumentsError(f"Tool arguments must use --name value syntax: {raw_argument}")

        if "=" in raw_argument:
            key, raw_value = raw_argument[2:].split("=", 1)
            value = _parse_json_value(raw_value)
            index += 1
        else:
            key = raw_argument[2:]
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
                value = _parse_json_value(tokens[index + 1])
                index += 2
            else:
                value = True
                index += 1

        key = _validate_argument_key(key)
        if key in arguments:
            raise ToolArgumentsError(f"Duplicate tool argument: {key}")
        arguments[key] = value
    return arguments


def _validate_argument_key(key: str) -> str:
    if not _ARGUMENT_KEY_RE.fullmatch(key):
        raise ToolArgumentsError(
            f"Invalid tool argument name: {key}. Use a top-level JSON property name or --args-json.",
        )
    return key


def _parse_json_value(raw_value: str) -> Any:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value
