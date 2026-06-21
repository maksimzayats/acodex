from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias, cast

ConfigPayload: TypeAlias = dict[str, Any]
SectionName: TypeAlias = Literal["server", "codex", "bridge"]

SERVER_SECTION: SectionName = "server"
CODEX_SECTION: SectionName = "codex"
BRIDGE_SECTION: SectionName = "bridge"


@dataclass(frozen=True, slots=True)
class EnvironmentField:
    section: SectionName
    key: str
    env_name: str
    caster: Callable[[str], str | int | float] = str

    def read(self) -> tuple[SectionName, str, Any] | None:
        """Read one environment override.

        Returns:
            Tuple with section, key, and typed setting value when present.

        """
        configured_value = os.environ.get(self.env_name)
        if configured_value is None:
            return None
        return self.section, self.key, self.caster(configured_value)


ENVIRONMENT_FIELDS: tuple[EnvironmentField, ...] = (
    EnvironmentField(SERVER_SECTION, "host", "ACODEX_SERVER_HOST"),
    EnvironmentField(SERVER_SECTION, "port", "ACODEX_SERVER_PORT", int),
    EnvironmentField(CODEX_SECTION, "app_path", "ACODEX_CODEX_APP_PATH"),
    EnvironmentField(CODEX_SECTION, "cdp_host", "ACODEX_CODEX_APP_CDP_HOST"),
    EnvironmentField(CODEX_SECTION, "cdp_port", "ACODEX_CODEX_APP_CDP_PORT", int),
    EnvironmentField(
        CODEX_SECTION,
        "request_timeout",
        "ACODEX_CODEX_APP_CDP_REQUEST_TIMEOUT",
        float,
    ),
    EnvironmentField(BRIDGE_SECTION, "host_id", "ACODEX_CODEX_APP_BRIDGE_HOST_ID"),
    EnvironmentField(
        BRIDGE_SECTION,
        "source_thread_id",
        "ACODEX_CODEX_APP_BRIDGE_SOURCE_THREAD_ID",
    ),
)


@dataclass(frozen=True, slots=True)
class EnvironmentOverrideProvider:
    """Build overrides from ACODEX_* environment variables."""

    fields: tuple[EnvironmentField, ...] = ENVIRONMENT_FIELDS

    def overrides(self) -> ConfigPayload:
        """Return environment overrides grouped by config section."""
        override_payload: ConfigPayload = _empty_override_payload(with_bridge=True)
        for environment_field in self.fields:
            field_value = environment_field.read()
            if field_value is None:
                continue
            section_name, setting_key, setting_value = field_value
            section_payload = cast(ConfigPayload, override_payload[section_name])
            section_payload[setting_key] = setting_value
        return override_payload


@dataclass(frozen=True, kw_only=True, slots=True)
class CliOverrideProvider:
    """Build overrides passed by CLI command flags."""

    server_host: str | None = None
    server_port: int | None = None
    codex_app_path: str | None = None
    cdp_port: int | None = None

    def overrides(self) -> ConfigPayload:
        """Return CLI overrides grouped by config section."""
        override_payload = _empty_override_payload(with_bridge=False)
        self._set_server_host(override_payload)
        self._set_server_port(override_payload)
        self._set_codex_app_path(override_payload)
        self._set_cdp_port(override_payload)
        return override_payload

    def _set_server_host(self, override_payload: ConfigPayload) -> None:
        if self.server_host is not None:
            cast(ConfigPayload, override_payload[SERVER_SECTION])["host"] = self.server_host

    def _set_server_port(self, override_payload: ConfigPayload) -> None:
        if self.server_port is not None:
            cast(ConfigPayload, override_payload[SERVER_SECTION])["port"] = self.server_port

    def _set_codex_app_path(self, override_payload: ConfigPayload) -> None:
        if self.codex_app_path is not None:
            cast(ConfigPayload, override_payload[CODEX_SECTION])["app_path"] = self.codex_app_path

    def _set_cdp_port(self, override_payload: ConfigPayload) -> None:
        if self.cdp_port is not None:
            cast(ConfigPayload, override_payload[CODEX_SECTION])["cdp_port"] = self.cdp_port


@dataclass(frozen=True, slots=True)
class ConfigMerger:
    """Merge nested config dictionaries while ignoring empty override sections."""

    def deep_merge(
        self,
        base_payload: ConfigPayload,
        override_payload: ConfigPayload,
    ) -> ConfigPayload:
        """Return a recursively merged config payload."""
        merged_payload = dict(base_payload)
        for setting_key, override_value in override_payload.items():
            existing_value = merged_payload.get(setting_key)
            if self._can_merge(override_value, existing_value):
                merged_payload[setting_key] = self.deep_merge(
                    cast(ConfigPayload, existing_value),
                    override_value,
                )
            elif override_value:
                merged_payload[setting_key] = override_value
        return merged_payload

    def _can_merge(self, override_value: Any, existing_value: Any) -> bool:
        return isinstance(override_value, dict) and isinstance(existing_value, dict)


def _empty_override_payload(*, with_bridge: bool) -> ConfigPayload:
    override_payload: ConfigPayload = {SERVER_SECTION: {}, CODEX_SECTION: {}}
    if with_bridge:
        override_payload[BRIDGE_SECTION] = {}
    return override_payload
