from __future__ import annotations

from dataclasses import dataclass

from diwire import Injected
from pydantic_settings import BaseSettings, SettingsConfigDict


class CodexCDPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACODEX_CODEX_APP_CDP_")

    host: str = "127.0.0.1"
    port: int = 5633
    request_timeout: float = 10.0

    @property
    def base_url(self) -> str:
        """Return the base URL for the Codex app CDP endpoint."""
        return f"http://{self.host}:{self.port}"


@dataclass(kw_only=True, slots=True)
class CodexCDPClient:
    _settings: Injected[CodexCDPSettings]


class CodexCDPError(RuntimeError):
    """Raised when the Codex renderer cannot be reached or evaluated."""
