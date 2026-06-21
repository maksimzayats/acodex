from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("~/.acodex/config.json")
CONFIG_ENV_NAME = "ACODEX_CONFIG"


@dataclass(frozen=True, slots=True)
class ConfigPathProvider:
    """Resolve acodex configuration paths."""

    env_name: str = CONFIG_ENV_NAME
    default_path: Path = DEFAULT_CONFIG_PATH

    def path(self) -> Path:
        """Return the effective config path."""
        configured_path = os.environ.get(self.env_name)
        if configured_path:
            return Path(configured_path).expanduser()
        return self.default_path.expanduser()

    def root(self, config_path: Path | None = None) -> Path:
        """Return the root directory for runtime state."""
        return (config_path or self.path()).parent


def get_config_path() -> Path:
    return ConfigPathProvider().path()


def config_root(config_path: Path | None = None) -> Path:
    return ConfigPathProvider().root(config_path)
