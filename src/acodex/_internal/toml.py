from __future__ import annotations

import json
import math
import re

_TOML_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def to_toml_value(value: object, path: str) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            msg = f"Codex config override at {path} must be a finite number"
            raise ValueError(msg)
        return str(value)
    if isinstance(value, list):
        return _render_list(value, path)
    if isinstance(value, dict):
        return _render_object(value, path)
    if value is None:
        msg = f"Codex config override at {path} cannot be null"
        raise ValueError(msg)

    type_name = type(value).__name__
    msg = f"Unsupported Codex config override value at {path}: {type_name}"
    raise ValueError(msg)


def _render_list(value: list[object], path: str) -> str:
    rendered = [to_toml_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    return f"[{', '.join(rendered)}]"


def _render_object(value: dict[object, object], path: str) -> str:
    parts: list[str] = []
    for key, child in value.items():
        if not isinstance(key, str) or not key:
            msg = "Codex config override keys must be non-empty strings"
            raise ValueError(msg)
        child_path = f"{path}.{key}"
        parts.append(f"{_format_toml_key(key)} = {to_toml_value(child, child_path)}")
    return f"{{{', '.join(parts)}}}"


def _format_toml_key(key: str) -> str:
    return key if _TOML_BARE_KEY.fullmatch(key) else json.dumps(key, ensure_ascii=False)
