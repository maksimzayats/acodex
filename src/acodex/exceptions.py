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


class CodexExecutableNotFoundError(CodexExecError):
    """Raised when the codex executable cannot be discovered on PATH."""

    def __init__(
        self,
        message: str,
        *,
        executable_name: str = "codex",
    ) -> None:
        super().__init__(message)
        self.executable_name = executable_name


class CodexThreadRunError(CodexError):
    """Raised when a thread run fails while streaming or parsing events."""


class CodexConfigError(CodexError):
    """Raised when Codex config overrides are invalid or cannot be serialized."""


class CodexOutputSchemaError(CodexError):
    """Raised when a TurnOptions.output_schema payload is invalid."""


class CodexInternalError(CodexError):
    """Raised when an internal invariant is violated, indicating a bug in acodex."""
