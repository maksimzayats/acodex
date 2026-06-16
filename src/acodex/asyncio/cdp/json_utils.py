from __future__ import annotations

import json
from typing import Any, Final

from acodex.asyncio.cdp.errors import CodexAppCdpProtocolError
from acodex.asyncio.cdp.types import JsonObject, JsonValue

_JSON_COMPACT_SEPARATORS: Final = (",", ":")


def dump_json(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=True, separators=_JSON_COMPACT_SEPARATORS)


def decode_json_object(message: str | bytes) -> JsonObject:
    value = decode_json_value(message)
    if not isinstance(value, dict):
        raise CodexAppCdpProtocolError("Expected a JSON object")
    return value


def decode_json_value(message: str | bytes) -> JsonValue:
    text = message.decode("utf-8") if isinstance(message, bytes) else message
    loaded: Any = json.loads(text)
    return ensure_json_value(loaded)


def ensure_json_value(value: Any) -> JsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [ensure_json_value(item) for item in value]
    if isinstance(value, dict):
        result: JsonObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CodexAppCdpProtocolError("JSON object keys must be strings")
            result[key] = ensure_json_value(item)
        return result
    raise CodexAppCdpProtocolError(f"Unsupported JSON value: {type(value).__name__}")
