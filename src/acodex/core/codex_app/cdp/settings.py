from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class CodexCDPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACODEX_CODEX_APP_CDP_")

    host: str = "127.0.0.1"
    port: int = 45217
    request_timeout: float = 10.0

    @property
    def base_url(self) -> str:
        """Return the base URL for the Codex app CDP endpoint."""
        return f"http://{self.host}:{self.port}"
