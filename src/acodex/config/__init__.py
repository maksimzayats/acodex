from __future__ import annotations

from acodex.config.compat import deep_merge as _deep_merge
from acodex.config.initializer import ConfigInitializer, init_config
from acodex.config.loader import ConfigFileReader, ConfigLoader, default_config, load_config
from acodex.config.models import (
    AcodexConfig,
    BridgeConfig,
    CodexConfig,
    ConfigError,
    ServerConfig,
)
from acodex.config.overrides import (
    CliOverrideProvider,
    ConfigMerger,
    EnvironmentField,
    EnvironmentOverrideProvider,
)
from acodex.config.paths import (
    DEFAULT_CONFIG_PATH,
    ConfigPathProvider,
    config_root,
    get_config_path,
)

__all__ = (
    "DEFAULT_CONFIG_PATH",
    "AcodexConfig",
    "BridgeConfig",
    "CliOverrideProvider",
    "CodexConfig",
    "ConfigError",
    "ConfigFileReader",
    "ConfigInitializer",
    "ConfigLoader",
    "ConfigMerger",
    "ConfigPathProvider",
    "EnvironmentField",
    "EnvironmentOverrideProvider",
    "ServerConfig",
    "_deep_merge",
    "config_root",
    "default_config",
    "get_config_path",
    "init_config",
    "load_config",
)
