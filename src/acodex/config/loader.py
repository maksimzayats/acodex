from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from acodex.config.models import AcodexConfig, ConfigError
from acodex.config.overrides import (
    CliOverrideProvider,
    ConfigMerger,
    EnvironmentOverrideProvider,
)
from acodex.config.paths import ConfigPathProvider


@dataclass(frozen=True, slots=True)
class ConfigFileReader:
    """Read a JSON config file into a dictionary payload."""

    def read(self, config_path: Path) -> dict[str, Any]:
        """Read a config payload from disk.

        Raises:
            ConfigError: If the config cannot be read or is not a JSON object.

        """
        try:
            file_payload = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in {config_path}: {exc.msg}") from exc
        except OSError as exc:
            raise ConfigError(f"Could not read config {config_path}: {exc}") from exc
        if not isinstance(file_payload, dict):
            raise ConfigError(f"Config {config_path} must contain a JSON object")
        return cast("dict[str, Any]", file_payload)


@dataclass(frozen=True, kw_only=True, slots=True)
class ConfigLoader:
    """Load the effective acodex config from all configured sources."""

    path_provider: ConfigPathProvider = field(default_factory=ConfigPathProvider)
    file_reader: ConfigFileReader = field(default_factory=ConfigFileReader)
    env_provider: EnvironmentOverrideProvider = field(default_factory=EnvironmentOverrideProvider)
    merger: ConfigMerger = field(default_factory=ConfigMerger)

    def load(
        self,
        *,
        config_path: Path | None = None,
        server_host: str | None = None,
        server_port: int | None = None,
        codex_app_path: str | None = None,
        cdp_port: int | None = None,
    ) -> AcodexConfig:
        """Return the effective config after applying all override layers."""
        resolved_path = config_path or self.path_provider.path()
        merged_payload = self._base_payload(resolved_path)
        cli_provider = CliOverrideProvider(
            server_host=server_host,
            server_port=server_port,
            codex_app_path=codex_app_path,
            cdp_port=cdp_port,
        )
        return self._validate(
            self.merger.deep_merge(
                self.merger.deep_merge(merged_payload, self.env_provider.overrides()),
                cli_provider.overrides(),
            ),
        )

    def _base_payload(self, config_path: Path) -> dict[str, Any]:
        base_payload = default_config().model_dump()
        if not config_path.exists():
            return base_payload
        return self.merger.deep_merge(base_payload, self.file_reader.read(config_path))

    def _validate(self, config_payload: dict[str, Any]) -> AcodexConfig:
        try:
            return AcodexConfig.model_validate(config_payload)
        except (ValidationError, ValueError) as exc:
            raise ConfigError(f"Invalid acodex config: {exc}") from exc


def default_config() -> AcodexConfig:
    return AcodexConfig()


def load_config(
    *,
    config_path: Path | None = None,
    server_host: str | None = None,
    server_port: int | None = None,
    codex_app_path: str | None = None,
    cdp_port: int | None = None,
) -> AcodexConfig:
    return ConfigLoader().load(
        config_path=config_path,
        server_host=server_host,
        server_port=server_port,
        codex_app_path=codex_app_path,
        cdp_port=cdp_port,
    )
