from __future__ import annotations

from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CDP_ENDPOINT: Final = "http://127.0.0.1:9222"
DEFAULT_CDP_TARGET_URL: Final = "app://-/index.html"
DEFAULT_CDP_TARGET_URL_PREFIX: Final = "app://"
DEFAULT_CDP_HTTP_TIMEOUT: Final = 10.0
DEFAULT_CDP_RUNTIME_TIMEOUT: Final = 30.0


class CodexAppCdpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACODEX_CDP_", extra="ignore")

    endpoint: str = DEFAULT_CDP_ENDPOINT
    target_url: str = DEFAULT_CDP_TARGET_URL
    target_url_prefix: str = DEFAULT_CDP_TARGET_URL_PREFIX
    http_timeout: float = Field(default=DEFAULT_CDP_HTTP_TIMEOUT, gt=0)
    runtime_timeout: float = Field(default=DEFAULT_CDP_RUNTIME_TIMEOUT, gt=0)
