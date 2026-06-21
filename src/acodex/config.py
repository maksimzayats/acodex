from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from acodex.core.codex_app.bridge import CodexAppBridgeSettings
from acodex.core.codex_app.cdp import CodexCDPSettings

DEFAULT_CONFIG_PATH = Path("~/.acodex/config.json")


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = 45218


class CodexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    host_id: str = "local"
    source_thread_id: str | None = None


class AcodexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


def default_config() -> AcodexConfig:
    return AcodexConfig()


def get_config_path() -> Path:
    configured = os.environ.get("ACODEX_CONFIG")
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_CONFIG_PATH.expanduser()


def config_root(config_path: Path | None = None) -> Path:
    return (config_path or get_config_path()).parent


def load_config(
    *,
    config_path: Path | None = None,
    server_host: str | None = None,
    server_port: int | None = None,
    codex_app_path: str | None = None,
    cdp_port: int | None = None,
) -> AcodexConfig:
    path = config_path or get_config_path()
    raw_config = default_config().model_dump()
    if path.exists():
        raw_config = _deep_merge(raw_config, _read_config_file(path))
    try:
        raw_config = _deep_merge(raw_config, _env_overrides())
        raw_config = _deep_merge(
            raw_config,
            _cli_overrides(
                server_host=server_host,
                server_port=server_port,
                codex_app_path=codex_app_path,
                cdp_port=cdp_port,
            ),
        )
        return AcodexConfig.model_validate(raw_config)
    except (ValidationError, ValueError) as exc:
        raise ConfigError(f"Invalid acodex config: {exc}") from exc


def init_config(*, config_path: Path | None = None) -> Path:
    path = config_path or get_config_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(default_config().model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _read_config_file(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc.msg}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Config {path} must contain a JSON object")
    return raw


def _env_overrides() -> dict[str, Any]:
    overrides: dict[str, Any] = {"server": {}, "codex": {}, "bridge": {}}
    _set_if_present(overrides["server"], "host", env_name="ACODEX_SERVER_HOST")
    _set_int_if_present(overrides["server"], "port", env_name="ACODEX_SERVER_PORT")
    _set_if_present(overrides["codex"], "app_path", env_name="ACODEX_CODEX_APP_PATH")
    _set_if_present(overrides["codex"], "cdp_host", env_name="ACODEX_CODEX_APP_CDP_HOST")
    _set_int_if_present(overrides["codex"], "cdp_port", env_name="ACODEX_CODEX_APP_CDP_PORT")
    _set_float_if_present(
        overrides["codex"],
        "request_timeout",
        env_name="ACODEX_CODEX_APP_CDP_REQUEST_TIMEOUT",
    )
    _set_if_present(
        overrides["bridge"],
        "host_id",
        env_name="ACODEX_CODEX_APP_BRIDGE_HOST_ID",
    )
    _set_if_present(
        overrides["bridge"],
        "source_thread_id",
        env_name="ACODEX_CODEX_APP_BRIDGE_SOURCE_THREAD_ID",
    )
    return overrides


def _cli_overrides(
    *,
    server_host: str | None,
    server_port: int | None,
    codex_app_path: str | None,
    cdp_port: int | None,
) -> dict[str, Any]:
    overrides: dict[str, Any] = {"server": {}, "codex": {}}
    if server_host is not None:
        overrides["server"]["host"] = server_host
    if server_port is not None:
        overrides["server"]["port"] = server_port
    if codex_app_path is not None:
        overrides["codex"]["app_path"] = codex_app_path
    if cdp_port is not None:
        overrides["codex"]["cdp_port"] = cdp_port
    return overrides


def _set_if_present(target: dict[str, Any], key: str, *, env_name: str) -> None:
    value = os.environ.get(env_name)
    if value is not None:
        target[key] = value


def _set_int_if_present(target: dict[str, Any], key: str, *, env_name: str) -> None:
    value = os.environ.get(env_name)
    if value is not None:
        target[key] = int(value)


def _set_float_if_present(target: dict[str, Any], key: str, *, env_name: str) -> None:
    value = os.environ.get(env_name)
    if value is not None:
        target[key] = float(value)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            merged[key] = _deep_merge(cast("dict[str, Any]", existing), value)
        elif value != {}:
            merged[key] = value
    return merged
