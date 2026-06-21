from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from diwire import Injected

from acodex.cli.tools.arguments import ToolArgumentsParser
from acodex.cli.tools.client_provider import ManagedMCPToolsClientProvider
from acodex.cli.tools.models import ToolOutput
from acodex.cli.tools.presenter import ToolsPresenter

IS_ERROR_KEY = "isError"


@dataclass(frozen=True, kw_only=True, slots=True)
class ToolsCommand:
    """Application service for `acodex tools` commands."""

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

        tool_arguments = self.parser.parse(
            raw_args,
            args_json=args_json,
            args_json_file=args_json_file,
        )
        tool_result: dict[str, Any] = client.call_tool(name, tool_arguments)
        self.presenter.tool_call_result(tool_result, output=output)
        return 1 if tool_result.get(IS_ERROR_KEY) is True else 0
