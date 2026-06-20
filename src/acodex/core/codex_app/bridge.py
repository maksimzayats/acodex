from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from diwire import Injected
from pydantic_settings import BaseSettings, SettingsConfigDict

from acodex.core.codex_app.assets import CodexRendererAssets, discover_renderer_assets
from acodex.core.codex_app.cdp import CodexCDPClient
from acodex.core.codex_app.renderer_bridge import renderer_expression
from acodex.core.codex_app.runtime_dependencies import (
    is_descriptor_without_handler,
    load_workspace_dependencies_fallback,
)


class CodexAppBridgeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACODEX_CODEX_APP_BRIDGE_")

    host_id: str = "local"
    source_thread_id: str | None = None


class CodexAppBridgeError(RuntimeError):
    """Raised when the Codex app bridge cannot discover or call a tool."""


@dataclass(kw_only=True, slots=True)
class CodexAppBridge:
    _cdp: Injected[CodexCDPClient]
    _settings: Injected[CodexAppBridgeSettings]
    _assets: CodexRendererAssets | None = field(default=None, init=False)

    async def list_tools(self) -> list[dict[str, Any]]:
        """List tools exposed by the Codex app.

        Returns:
            MCP-compatible Codex app tool descriptors.

        """
        result = await self._evaluate({"action": "listTools"})
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            return []
        return [tool for tool in tools if isinstance(tool, dict)]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Call a tool exposed by the Codex app.

        Returns:
            The raw Codex app tool result.

        """
        raw_name = normalize_tool_name(name)
        result = await self._evaluate(
            {
                "action": "callTool",
                "toolName": raw_name,
                "arguments": arguments or {},
            },
        )
        tool_result = result.get("result")
        if not isinstance(tool_result, dict):
            return {
                "success": False,
                "contentItems": [{"type": "inputText", "text": str(tool_result)}],
            }
        if raw_name == "load_workspace_dependencies" and is_descriptor_without_handler(tool_result):
            return load_workspace_dependencies_fallback()
        return tool_result

    async def _evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        assets = await self._get_assets()
        bridge_payload = {
            **payload,
            "assets": assets.as_payload(),
            "hostId": self._settings.host_id,
            "sourceThreadId": self._settings.source_thread_id,
        }
        result = await self._cdp.evaluate(renderer_expression(bridge_payload), await_promise=True)
        if isinstance(result, str):
            result = json.loads(result)
        if not isinstance(result, dict):
            raise CodexAppBridgeError(f"Unexpected Codex bridge result: {result!r}")
        if not result.get("ok"):
            raise CodexAppBridgeError(str(result.get("error") or "Codex bridge failed"))
        return result

    async def _get_assets(self) -> CodexRendererAssets:
        if self._assets is None:
            self._assets = await discover_renderer_assets(self._cdp)
        return self._assets


def normalize_tool_name(name: str) -> str:
    if name.startswith("codex_app."):
        return name.removeprefix("codex_app.")
    if name.startswith("codex_app__"):
        return name.removeprefix("codex_app__")
    return name
