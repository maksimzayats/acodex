from __future__ import annotations

from enum import StrEnum


class ToolOutput(StrEnum):
    text = "text"
    json = "json"


class ToolArgumentsError(ValueError):
    """Raised when tool arguments cannot be parsed from CLI tokens."""
