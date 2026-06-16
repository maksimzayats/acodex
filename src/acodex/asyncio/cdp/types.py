from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias

JsonValue: TypeAlias = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None
JsonObject: TypeAlias = dict[str, JsonValue]
ThinkingEffort: TypeAlias = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True, slots=True)
class CdpTarget:
    id: str
    kind: str
    url: str
    websocket_debugger_url: str


@dataclass(frozen=True, slots=True)
class CodexAppToolDiscovery:
    tool_names: tuple[str, ...]
    missing_tool_names: tuple[str, ...]
    tool_exports: Mapping[str, str]
    tool_chunk_urls: tuple[str, ...]
    rpc_chunk_urls: tuple[str, ...]
