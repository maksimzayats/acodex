from dataclasses import dataclass
from typing import Any

from diwire import Injected
from pydantic_settings import BaseSettings, SettingsConfigDict

from acodex.core.codex_app.cdp import CodexCDPClient


class CodexAppBridgeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACODEX_CODEX_APP_BRIDGE_")

    host_id: str = "local"
    source_thread_id: str | None = None


@dataclass(kw_only=True, slots=True)
class CodexAppBridge:
    _cdp: Injected[CodexCDPClient]
    _settings: Injected[CodexAppBridgeSettings]

    async def list_tools(self) -> list[dict[str, Any]]:
        ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None,
    ) -> dict[str, Any]:
        ...
