from __future__ import annotations

from typing import Any

from acodex.config.overrides import ConfigMerger


def deep_merge(base_payload: dict[str, Any], override_payload: dict[str, Any]) -> dict[str, Any]:
    return ConfigMerger().deep_merge(base_payload, override_payload)
