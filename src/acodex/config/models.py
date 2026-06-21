from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from acodex.core.codex_app.bridge import CodexAppBridgeSettings
from acodex.core.codex_app.cdp import CodexCDPSettings

FORBID_EXTRA: Literal["forbid"] = "forbid"


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra=FORBID_EXTRA)

    host: str = "127.0.0.1"
    port: int = 45218


class CodexConfig(BaseModel):
    model_config = ConfigDict(extra=FORBID_EXTRA)

    app_path: str = "/Applications/Codex.app"
    cdp_host: str = "127.0.0.1"
    cdp_port: int = 45217
    request_timeout: float = 10.0
    launch_timeout: float = 20.0

    @property
    def cdp_url(self) -> str:
        """Return the configured CDP base URL."""
        return f"http://{self.cdp_host}:{self.cdp_port}"


class BridgeConfig(BaseModel):
    model_config = ConfigDict(extra=FORBID_EXTRA)

    host_id: str = "local"
    source_thread_id: str | None = None


class AcodexConfig(BaseModel):
    model_config = ConfigDict(extra=FORBID_EXTRA)

    server: ServerConfig = Field(default_factory=ServerConfig)
    codex: CodexConfig = Field(default_factory=CodexConfig)
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)

    def to_cdp_settings(self) -> CodexCDPSettings:
        """Convert effective config into CDP settings.

        Returns:
            Settings consumed by the CDP client.

        """
        return CodexCDPSettings(
            host=self.codex.cdp_host,
            port=self.codex.cdp_port,
            request_timeout=self.codex.request_timeout,
        )

    def to_bridge_settings(self) -> CodexAppBridgeSettings:
        """Convert effective config into bridge settings.

        Returns:
            Settings consumed by the Codex app bridge.

        """
        return CodexAppBridgeSettings(
            host_id=self.bridge.host_id,
            source_thread_id=self.bridge.source_thread_id,
        )


class ConfigError(RuntimeError):
    """Raised when the acodex config cannot be read or validated."""
