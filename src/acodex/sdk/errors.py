from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from acodex.sdk.models import ToolResult


class AcodexSDKError(RuntimeError):
    """Base error raised by the public acodex SDK."""


class AcodexConnectionError(AcodexSDKError):
    """Raised when the SDK cannot connect to or use the MCP transport."""


class AcodexResultError(AcodexSDKError):
    """Raised when a tool result cannot be converted to the requested shape."""


class AcodexToolError(AcodexSDKError):
    """Raised when an MCP tool call fails at the protocol or tool-result layer."""

    def __init__(
        self,
        message: str,
        *,
        result: ToolResult | None = None,
        code: int | None = None,
        data: Any = None,
    ) -> None:
        self.result = result
        self.code = code
        self.data = data
        super().__init__(message)
