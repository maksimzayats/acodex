from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from acodex.cli.tools.descriptors import (
    DESCRIPTION_KEY,
    NAME_KEY,
    ToolDescriptorCatalog,
    ToolResultFormatter,
    json_syntax,
    mcp_tool_result_shape,
    panel,
    tool_output_note,
)
from acodex.cli.tools.models import ToolOutput


@dataclass(kw_only=True, slots=True)
class ToolsPresenter:
    """Render MCP tools command output."""

    console: Console = field(default_factory=Console)
    descriptor_catalog: ToolDescriptorCatalog = field(default_factory=ToolDescriptorCatalog)
    result_formatter: ToolResultFormatter = field(default_factory=ToolResultFormatter)

    def json(self, json_payload: Any) -> None:
        """Print a payload as formatted JSON."""
        self.console.print_json(json.dumps(json_payload, indent=2))

    def tools_list(self, tools: list[dict[str, Any]]) -> None:
        """Print the human-readable tools list."""
        if not tools:
            self.warning("No tools are currently exposed")
            return
        self.console.print(panel("Codex Tools", self._tools_table(tools)))

    def tool_help(self, *, name: str, tools: list[dict[str, Any]]) -> None:
        """Print help for a single MCP tool descriptor.

        Raises:
            ValueError: If the requested tool is not present in the tool descriptors.

        """
        descriptor_payload = self.descriptor_catalog.find_descriptor(tools, name)
        if descriptor_payload is None:
            raise ValueError(f"Tool not found: {name}")
        self.console.print(panel("Tool Help", self._summary_table(name, descriptor_payload)))
        self.console.print(
            panel("Input schema", json_syntax(descriptor_payload.get("inputSchema", {}))),
        )
        self._print_output_shape(descriptor_payload)
        self.console.print(
            panel("Raw MCP result (--output json)", json_syntax(mcp_tool_result_shape())),
        )

    def tool_call_result(self, tool_result: dict[str, Any], *, output: ToolOutput) -> None:
        """Print a tool call result in the requested output format."""
        if output == ToolOutput.json:
            self.json(tool_result)
            return
        rendered_text = self.result_formatter.text(tool_result)
        if rendered_text:
            self.console.print(rendered_text, markup=False, highlight=False, soft_wrap=True)

    def warning(self, message: str, detail: str | None = None) -> None:
        """Print a warning message."""
        warning_text = Text(message, style="bold yellow")
        if detail is not None:
            warning_text.append(f"\n{detail}", style="cyan")
        self.console.print(warning_text)

    def _tools_table(self, tools: list[dict[str, Any]]) -> Table:
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Description", overflow="fold")
        for descriptor_payload in tools:
            table.add_row(
                str(descriptor_payload.get(NAME_KEY, "")),
                str(descriptor_payload.get(DESCRIPTION_KEY, "")),
            )
        return table

    def _summary_table(self, name: str, descriptor_payload: dict[str, Any]) -> Table:
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column(style="bold", no_wrap=True)
        table.add_column(ratio=1, overflow="fold")
        table.add_row("Name", str(descriptor_payload.get(NAME_KEY, name)))
        table.add_row("Description", str(descriptor_payload.get(DESCRIPTION_KEY, "")))
        table.add_row("Usage", f"acodex tools call {name} --argument value")
        return table

    def _print_output_shape(self, descriptor_payload: dict[str, Any]) -> None:
        output_shape = self.descriptor_catalog.output_shape(descriptor_payload)
        if output_shape is None:
            self.console.print(panel("Default output", tool_output_note()))
            return
        self.console.print(panel("Default output payload shape", json_syntax(output_shape)))
