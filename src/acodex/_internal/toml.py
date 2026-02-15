from __future__ import annotations

import json
import math
import re
from typing import Any, TypeGuard, cast

from acodex.types.codex_options import CodexConfigObject, CodexConfigValue

_TOML_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def serialize_config_overrides(config_overrides: CodexConfigObject) -> list[str]:
    overrides: list[str] = []
    _flatten_config_overrides(config_overrides, "", overrides=overrides)
    return overrides


def to_toml_value(value: CodexConfigValue, path: str) -> str:
    raw_value: Any = value

    if isinstance(raw_value, str):
        return json.dumps(raw_value, ensure_ascii=False)
    if isinstance(raw_value, bool):
        return "true" if raw_value else "false"
    if isinstance(raw_value, int):
        return str(raw_value)
    if isinstance(raw_value, float):
        if not math.isfinite(raw_value):
            msg = f"Codex config override at {path} must be a finite number"
            raise ValueError(msg)
        return str(raw_value)
    if isinstance(raw_value, list):
        return _render_list(raw_value, path)
    if isinstance(raw_value, dict):
        return _render_object(raw_value, path)
    if raw_value is None:
        msg = f"Codex config override at {path} cannot be null"
        raise ValueError(msg)

    type_name = type(raw_value).__name__
    msg = f"Unsupported Codex config override value at {path}: {type_name}"
    raise ValueError(msg)


def _render_list(value: list[CodexConfigValue], path: str) -> str:
    rendered = [to_toml_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    return f"[{', '.join(rendered)}]"


def _render_object(value: CodexConfigObject, path: str) -> str:
    parts: list[str] = []
    for key, child in cast("dict[Any, Any]", value).items():
        if not isinstance(key, str) or not key:
            msg = "Codex config override keys must be non-empty strings"
            raise ValueError(msg)
        child_path = f"{path}.{key}"
        parts.append(f"{_format_toml_key(key)} = {to_toml_value(child, child_path)}")
    return f"{{{', '.join(parts)}}}"


def _flatten_config_overrides(
    value: CodexConfigValue,
    prefix: str,
    *,
    overrides: list[str],
) -> None:
    raw_value: Any = value
    if not _is_plain_object(raw_value):
        if prefix:
            overrides.append(f"{prefix}={to_toml_value(raw_value, prefix)}")
            return

        msg = "Codex config overrides must be a plain object"
        raise ValueError(msg)

    entries = list(cast("dict[Any, Any]", raw_value).items())
    if not prefix and not entries:
        return
    if prefix and not entries:
        overrides.append(f"{prefix}={{}}")
        return

    for key, child in entries:
        if not isinstance(key, str) or not key:
            msg = "Codex config override keys must be non-empty strings"
            raise ValueError(msg)

        path = f"{prefix}.{key}" if prefix else key
        _flatten_config_overrides(child, path, overrides=overrides)


def _is_plain_object(value: CodexConfigValue) -> TypeGuard[CodexConfigObject]:
    return isinstance(value, dict)


def _format_toml_key(key: str) -> str:
    return key if _TOML_BARE_KEY.fullmatch(key) else json.dumps(key, ensure_ascii=False)
