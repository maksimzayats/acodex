from __future__ import annotations

from pathlib import Path
from shutil import which

from acodex.exceptions import CodexExecutableNotFoundError


def find_codex_path() -> str:
    """Resolve the Codex CLI executable path from PATH.

    Returns:
        The discovered executable path as a string.

    Raises:
        CodexExecutableNotFoundError: If ``codex`` is not discoverable on ``PATH``.

    """
    # NOTE: The Windows Python<3.12 deprecation is for PathLike `cmd` values; we pass a plain
    # string literal ("codex"), so it does not apply here.
    found = which("codex")
    if found is None:
        raise CodexExecutableNotFoundError(
            'Could not locate "codex" on PATH. Install the Codex CLI or pass `codex_path_override`.',
        )

    return str(Path(found))
