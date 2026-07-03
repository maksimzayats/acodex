from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from mcp.types import CallToolResult

from acodex.sdk.errors import AcodexResultError

CONTENT_TEXT_TYPE = "text"
DEFAULT_MCP_URL = "http://127.0.0.1:45218/mcp"
DEFAULT_TIMEOUT = 30.0
TEXT_KEY = "text"
TYPE_KEY = "type"


@dataclass(frozen=True, kw_only=True, slots=True)
class ToolResult:
    """Public SDK representation of an MCP tool result."""

    content_items: list[dict[str, Any]]
    is_error: bool
    structured_content: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None

    @classmethod
    def from_mcp(cls, result: CallToolResult) -> ToolResult:
        """Build a public result from the official MCP result model."""
        return cls(
            content_items=[
                content_item.model_dump(mode="json", by_alias=True, exclude_none=True)
                for content_item in result.content
            ],
            is_error=result.isError,
            structured_content=result.structuredContent,
            meta=result.meta,
        )

    def text(self) -> str:
        """Return joined text content from the result."""
        text_items = [
            content_item[TEXT_KEY]
            for content_item in self.content_items
            if self._is_text_content(content_item)
        ]
        if not text_items:
            raise AcodexResultError("Tool result did not include text content")
        return "\n".join(text_items)

    def json_object(self) -> dict[str, Any]:
        """Return a JSON object from structured content or text content."""
        if self.structured_content is not None:
            return self.structured_content
        try:
            json_payload = json.loads(self.text())
        except json.JSONDecodeError as exc:
            raise AcodexResultError("Tool text content is not valid JSON") from exc
        if not isinstance(json_payload, dict):
            raise AcodexResultError("Tool JSON content must be an object")
        return cast("dict[str, Any]", json_payload)

    def _is_text_content(self, content_item: dict[str, Any]) -> bool:
        return content_item.get(TYPE_KEY) == CONTENT_TEXT_TYPE and isinstance(
            content_item.get(TEXT_KEY), str
        )
