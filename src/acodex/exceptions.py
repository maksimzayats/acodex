from __future__ import annotations


class CodexError(Exception):
    """Base exception for all errors raised by acodex."""


class CodexCancelledError(CodexError):
    """Raised when a turn is canceled via TurnOptions.signal."""


class CodexExecError(CodexError):
    """Raised when the codex executable fails to start or exits unsuccessfully."""

    def __init__(self, message: str, *, stderr: str | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr


class CodexThreadRunError(CodexError):
    """Raised when a thread run fails while streaming or parsing events."""
