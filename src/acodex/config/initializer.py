from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from acodex.config.loader import default_config
from acodex.config.paths import ConfigPathProvider


@dataclass(frozen=True, kw_only=True, slots=True)
class ConfigInitializer:
    """Create the default acodex config file when it is missing."""

    path_provider: ConfigPathProvider = field(default_factory=ConfigPathProvider)

    def init(self, *, config_path: Path | None = None) -> Path:
        """Initialize the config file and return its path."""
        resolved_path = config_path or self.path_provider.path()
        if resolved_path.exists():
            return resolved_path
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(self._default_config_json(), encoding="utf-8")
        return resolved_path

    def _default_config_json(self) -> str:
        return "{}\n".format(json.dumps(default_config().model_dump(mode="json"), indent=2))


def init_config(*, config_path: Path | None = None) -> Path:
    return ConfigInitializer().init(config_path=config_path)
