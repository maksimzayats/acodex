from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

CONTENT_KEY = "content"
CONTENT_ITEMS_KEY = "contentItems"
IS_ERROR_KEY = "isError"
SUCCESS_KEY = "success"
TEXT_KEY = "text"
TYPE_KEY = "type"
INPUT_TEXT_TYPE = "inputText"
TEXT_TYPE = "text"


@dataclass(frozen=True, slots=True)
class MCPResultAdapter:
    """Adapt raw Codex app tool results to MCP tool result payloads."""

    def adapt(self, codex_result: dict[str, Any]) -> dict[str, Any]:
        """Return an MCP-compatible tool result."""
        if CONTENT_KEY in codex_result:
            return self._existing_content(codex_result)

        content_items = codex_result.get(CONTENT_ITEMS_KEY)
        content_payloads = self._content_items(content_items)
        if not content_payloads:
            content_payloads = [self._text_payload(json.dumps(codex_result, ensure_ascii=False))]

        return {
            CONTENT_KEY: content_payloads,
            IS_ERROR_KEY: codex_result.get(SUCCESS_KEY) is False,
        }

    def content_item(self, content_item: Any) -> dict[str, Any]:
        """Adapt one Codex content item to MCP text content."""
        if not isinstance(content_item, dict):
            return self._text_payload(str(content_item))
        item_payload = cast("dict[str, Any]", content_item)
        if item_payload.get(TYPE_KEY) == INPUT_TEXT_TYPE:
            return self._text_payload(str(item_payload.get(TEXT_KEY, "")))
        if isinstance(item_payload.get(TEXT_KEY), str):
            return self._text_payload(str(item_payload[TEXT_KEY]))
        return self._text_payload(json.dumps(item_payload, ensure_ascii=False))

    def _existing_content(self, codex_result: dict[str, Any]) -> dict[str, Any]:
        existing_content = codex_result[CONTENT_KEY]
        if isinstance(existing_content, list):
            content_payload = cast("list[dict[str, Any]]", existing_content)
        else:
            content_payload = [self._text_payload(str(existing_content))]
        return {
            CONTENT_KEY: content_payload,
            IS_ERROR_KEY: bool(codex_result.get(IS_ERROR_KEY)),
        }

    def _content_items(self, content_items: Any) -> list[dict[str, Any]]:
        if not isinstance(content_items, list):
            return []
        item_payloads = cast("list[Any]", content_items)  # type: ignore[redundant-cast]
        return [self.content_item(content_item) for content_item in item_payloads]

    def _text_payload(self, text_payload: str) -> dict[str, Any]:
        return {TYPE_KEY: TEXT_TYPE, TEXT_KEY: text_payload}
