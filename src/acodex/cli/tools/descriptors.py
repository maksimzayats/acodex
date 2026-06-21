from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from rich import box
from rich.console import RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

CONTENT_KEY = "content"
DESCRIPTION_KEY = "description"
IS_ERROR_KEY = "isError"
NAME_KEY = "name"
TEXT_KEY = "text"
TYPE_KEY = "type"
TEXT_TYPE = "text"

LIST_THREADS_TOOL = "codex_app.list_threads"


@dataclass(frozen=True, slots=True)
class ToolDescriptorCatalog:
    """Search and summarize MCP tool descriptors."""

    def find_descriptor(
        self,
        tools: list[dict[str, Any]],
        requested_name: str,
    ) -> dict[str, Any] | None:
        """Find a descriptor using dotted, bare, or double-underscore names."""
        normalized_name = requested_name.replace("codex_app__", "codex_app.", 1)
        bare_name = normalized_name.removeprefix("codex_app.")
        candidate_names = {normalized_name, f"codex_app.{bare_name}"}
        for descriptor_payload in tools:
            if descriptor_payload.get(NAME_KEY) in candidate_names:
                return descriptor_payload
        return None

    def output_shape(self, descriptor_payload: dict[str, Any]) -> dict[str, Any] | None:
        """Return the declared or known output shape for a descriptor."""
        output_schema = descriptor_payload.get("outputSchema")
        if isinstance(output_schema, dict):
            return cast("dict[str, Any]", output_schema)
        tool_name = descriptor_payload.get(NAME_KEY)
        if tool_name == LIST_THREADS_TOOL:
            return list_threads_output_shape()
        return None


@dataclass(frozen=True, slots=True)
class ToolResultFormatter:
    """Convert raw MCP tool results into CLI text."""

    def text(self, tool_result: dict[str, Any]) -> str:
        """Return the human-readable text for a tool result."""
        content_items = tool_result.get(CONTENT_KEY)
        if not isinstance(content_items, list):
            return json.dumps(tool_result, ensure_ascii=False)
        content_payloads = cast("list[Any]", content_items)  # type: ignore[redundant-cast]
        rendered_lines = [
            self._content_item_text(content_item) for content_item in content_payloads
        ]
        return "\n".join(rendered_lines)

    def _content_item_text(self, content_item: Any) -> str:
        if isinstance(content_item, dict):
            content_payload = cast("dict[str, Any]", content_item)
            if content_payload.get(TYPE_KEY) == TEXT_TYPE and isinstance(
                content_payload.get(TEXT_KEY), str
            ):
                return str(content_payload[TEXT_KEY])
        return json.dumps(content_item, ensure_ascii=False)


def find_tool_descriptor(tools: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return ToolDescriptorCatalog().find_descriptor(tools, name)


def json_syntax(json_payload: Any) -> Syntax:
    return Syntax(json.dumps(json_payload, indent=2, ensure_ascii=False), "json", word_wrap=True)


def tool_output_shape(descriptor_payload: dict[str, Any]) -> dict[str, Any] | None:
    return ToolDescriptorCatalog().output_shape(descriptor_payload)


def tool_output_note() -> Text:
    return Text(
        "This tool descriptor does not declare an output schema. "
        "Default output prints text content from the MCP result; use --output json for the raw wrapper.",
    )


def tool_result_text(tool_result: dict[str, Any]) -> str:
    return ToolResultFormatter().text(tool_result)


def mcp_tool_result_shape() -> dict[str, Any]:
    return {
        CONTENT_KEY: [{TYPE_KEY: TEXT_TYPE, TEXT_KEY: "..."}],
        IS_ERROR_KEY: False,
    }


def list_threads_output_shape() -> dict[str, Any]:
    return {
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
    }


def panel(title: str, renderable: RenderableType) -> Panel:
    return Panel(
        renderable,
        title=title,
        title_align="left",
        box=box.ROUNDED,
        border_style="dim",
        padding=(0, 1),
    )
