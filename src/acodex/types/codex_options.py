from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias, TypedDict

if TYPE_CHECKING:
    from typing_extensions import NotRequired

# fmt: off
CodexConfigValue: TypeAlias = str | int | float | bool | list["CodexConfigValue"] | dict[str, "CodexConfigValue"]
CodexConfigObject: TypeAlias = dict[str, CodexConfigValue]
# fmt: on


class CodexOptions(TypedDict):
    """Options used to construct a Codex client."""

    codex_path_override: NotRequired[str]
    """Optional path to the Codex executable."""

    base_url: NotRequired[str]
    """Optional base URL used by Codex API calls."""

    api_key: NotRequired[str]
    """Optional API key used by Codex API calls."""

    config: NotRequired[CodexConfigObject]
    """Additional ``--config key=value`` overrides passed to Codex CLI.

    Provide a JSON-like object and the SDK will flatten dotted paths and serialize values as TOML
    literals for CLI compatibility.
    """

    env: NotRequired[dict[str, str]]
    """Environment variables passed to the Codex CLI process.

    When provided, the SDK does not inherit from the current process environment.
    """
