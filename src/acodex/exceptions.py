from __future__ import annotations


class CodexError(Exception):
    """Base exception for all errors raised by acodex."""


class CodexCancelledError(CodexError):
    """Raised when a turn is canceled via TurnOptions.signal."""


class CodexExecError(CodexError):
    """Raised when the codex executable fails to start or exits unsuccessfully.

    Captured process output is available on ``stdout`` and ``stderr`` when present.
    """

    def __init__(
        self,
        message: str,
        *,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> None:
        super().__init__(_format_exec_error_message(message, stdout=stdout, stderr=stderr))
        self.stdout = stdout
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


class CodexThreadStreamNotConsumedError(CodexThreadRunError):
    """Raised when streamed.result is accessed before streamed.events is exhausted."""


class CodexStructuredResponseError(CodexThreadRunError):
    """Raised when structured output cannot be created or accessed."""


class CodexConfigError(CodexError):
    """Raised when Codex config overrides are invalid or cannot be serialized."""


class CodexOutputSchemaError(CodexError):
    """Raised when a TurnOptions.output_schema payload is invalid."""


class CodexInternalError(CodexError):
    """Raised when an internal invariant is violated, indicating a bug in acodex."""


def _format_exec_error_message(
    message: str,
    *,
    stdout: str | None,
    stderr: str | None,
) -> str:
    sections = [message]

    normalized_stdout = _normalize_exec_output(stdout)
    if normalized_stdout is not None:
        sections.extend(("", "STDOUT:", normalized_stdout))

    normalized_stderr = _normalize_exec_output(stderr)
    if normalized_stderr is not None:
        sections.extend(("", "STDERR:", normalized_stderr))

    return "\n".join(sections)


def _normalize_exec_output(output: str | None) -> str | None:
    if output is None:
        return None

    normalized_output = output.rstrip("\r\n")
    if not normalized_output:
        return None

    return normalized_output
