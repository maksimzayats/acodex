from __future__ import annotations

import os
import signal
import subprocess  # noqa: S404
from typing import BinaryIO


class ProcessOps:
    """Operate on managed server processes."""

    __slots__ = ()

    def is_running(self, pid: int) -> bool:
        """Return whether a process id appears to still be alive."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def spawn(self, command: list[str], log_file: BinaryIO) -> int:
        """Spawn the managed server as a detached child process."""
        process = subprocess.Popen(  # noqa: S603 - command is local executable/options.
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return process.pid

    def terminate(self, pid: int) -> None:
        """Send SIGTERM to the managed process."""
        os.kill(pid, signal.SIGTERM)

    def kill(self, pid: int) -> None:
        """Send SIGKILL to the managed process."""
        os.kill(pid, signal.SIGKILL)
