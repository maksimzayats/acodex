from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias, TypedDict

if TYPE_CHECKING:
    from typing import NotRequired

# fmt: off
CodexConfigValue: TypeAlias = str | int | float | bool | list["CodexConfigValue"] | dict[str, "CodexConfigValue"]
CodexConfigObject: TypeAlias = dict[str, CodexConfigValue]
# fmt: on


class CodexOptions(TypedDict):
    codex_path_override: NotRequired[str]
    base_url: NotRequired[str]
    api_key: NotRequired[str]
    config: NotRequired[CodexConfigObject]
    env: NotRequired[dict[str, str]]
