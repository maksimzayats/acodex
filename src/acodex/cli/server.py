from __future__ import annotations

import json
import os
import signal
import socket
import subprocess  # noqa: S404
import sys
import time
import urllib.error
import urllib.request
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from acodex.config import AcodexConfig, config_root

HTTP_OK = 200
HTTP_REDIRECT = 300


class ServerError(RuntimeError):
    """Raised when the managed HTTP server cannot be controlled."""


@dataclass(frozen=True, kw_only=True, slots=True)
class ServerState:
    pid: int
    host: str
    port: int
    base_url: str
    mcp_url: str
    started_at: float
    log_path: str
    command: list[str]

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> ServerState:
        """Build managed server state from persisted JSON.

        Returns:
            Parsed server state.

        """
        return cls(
            pid=int(payload["pid"]),
            host=str(payload["host"]),
            port=int(payload["port"]),
            base_url=str(payload["base_url"]),
            mcp_url=str(payload["mcp_url"]),
            started_at=float(payload["started_at"]),
            log_path=str(payload["log_path"]),
            command=[str(part) for part in payload.get("command", [])],
        )

    def to_json(self) -> dict[str, Any]:
        """Serialize managed server state to JSON-compatible values.

        Returns:
            JSON-compatible server state.

        """
        return {
            "pid": self.pid,
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url,
            "mcp_url": self.mcp_url,
            "started_at": self.started_at,
            "log_path": self.log_path,
            "command": self.command,
        }


@dataclass(frozen=True, kw_only=True, slots=True)
class ServerPaths:
    state_path: Path
    log_path: Path


class ProcessOps:
    def is_running(self, pid: int) -> bool:  # noqa: PLR6301
        """Return whether a process id appears to still be alive.

        Returns:
            True when the process exists or cannot be inspected due to permissions.

        """
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def spawn(self, command: list[str], log_file: BinaryIO) -> int:  # noqa: PLR6301
        """Spawn the managed server as a detached child process.

        Returns:
            Child process id.

        """
        process = subprocess.Popen(  # noqa: S603 - command is built from local executable/options.
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return int(process.pid)

    def terminate(self, pid: int) -> None:  # noqa: PLR6301
        """Send SIGTERM to the managed process."""
        os.kill(pid, signal.SIGTERM)

    def kill(self, pid: int) -> None:  # noqa: PLR6301
        """Send SIGKILL to the managed process."""
        os.kill(pid, signal.SIGKILL)


class HttpProbe:
    def reachable(self, url: str, *, timeout: float) -> bool:  # noqa: PLR6301
        """Return whether an HTTP endpoint responds with a 2xx status.

        Returns:
            True when the endpoint responds successfully.

        """
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
                return HTTP_OK <= response.status < HTTP_REDIRECT
        except (OSError, urllib.error.URLError):
            return False

    def mcp_initialize(self, mcp_url: str, *, timeout: float) -> bool:  # noqa: PLR6301
        """Run a minimal MCP initialize request against the HTTP server.

        Returns:
            True when MCP initialize receives a successful HTTP response.

        """
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "doctor",
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26"},
            },
        ).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310
            mcp_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return HTTP_OK <= response.status < HTTP_REDIRECT
        except (OSError, urllib.error.URLError):
            return False


@dataclass(kw_only=True, slots=True)
class ServerManager:
    config_path: Path | None = None
    process_ops: ProcessOps = field(default_factory=ProcessOps)
    http_probe: HttpProbe = field(default_factory=HttpProbe)
    poll_interval: float = 0.1

    @property
    def paths(self) -> ServerPaths:
        """Return runtime paths derived from the effective config path."""
        root = config_root(self.config_path)
        return ServerPaths(
            state_path=root / "run" / "server.json",
            log_path=root / "logs" / "server.log",
        )

    def start(self, config: AcodexConfig) -> ServerState:
        """Start the managed uvicorn server and persist its state.

        Returns:
            Persisted managed server state.

        Raises:
            ServerError: If an existing server, port conflict, or health failure blocks startup.

        """
        current = self.read_state()
        if current is not None:
            if self.process_ops.is_running(current.pid):
                raise ServerError(f"Managed server is already running at {current.base_url}")
            self.paths.state_path.unlink(missing_ok=True)

        if self._port_in_use(config.server.host, config.server.port):
            raise ServerError(f"Port {config.server.host}:{config.server.port} is already in use")

        paths = self.paths
        paths.state_path.parent.mkdir(parents=True, exist_ok=True)
        paths.log_path.parent.mkdir(parents=True, exist_ok=True)
        base_url = f"http://{config.server.host}:{config.server.port}"
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "acodex.http.app:app",
            "--host",
            config.server.host,
            "--port",
            str(config.server.port),
        ]
        with paths.log_path.open("ab") as log_file:
            pid = self.process_ops.spawn(command, log_file)
        state = ServerState(
            pid=pid,
            host=config.server.host,
            port=config.server.port,
            base_url=base_url,
            mcp_url=f"{base_url}/mcp",
            started_at=time.time(),
            log_path=str(paths.log_path),
            command=command,
        )
        self._write_state(state)
        if not self.wait_for_health(state, timeout=5.0):
            self._cleanup_failed_start(state)
            raise ServerError(f"Server did not become healthy. See logs at {paths.log_path}")
        return state

    def stop(self, *, force: bool) -> bool:
        """Stop the managed server if it is running.

        Returns:
            True when a running process was stopped.

        Raises:
            ServerError: If the process does not exit and force is false.

        """
        state = self.read_state()
        if state is None:
            return False
        if not self.process_ops.is_running(state.pid):
            self.paths.state_path.unlink(missing_ok=True)
            return False

        self.process_ops.terminate(state.pid)
        if self._wait_for_exit(state.pid, timeout=5.0):
            self.paths.state_path.unlink(missing_ok=True)
            return True
        if not force:
            raise ServerError(f"Server PID {state.pid} did not exit; retry with --force")
        self.process_ops.kill(state.pid)
        self._wait_for_exit(state.pid, timeout=2.0)
        self.paths.state_path.unlink(missing_ok=True)
        return True

    def status(self) -> dict[str, Any]:
        """Return current managed server status.

        Returns:
            JSON-compatible status fields.

        """
        state = self.read_state()
        if state is None:
            return {"running": False, "managed": False, "state_path": str(self.paths.state_path)}
        running = self.process_ops.is_running(state.pid)
        healthz = running and self.http_probe.reachable(f"{state.base_url}/healthz", timeout=1.0)
        if not running:
            self.paths.state_path.unlink(missing_ok=True)
        return {
            "running": running,
            "managed": True,
            "healthy": healthz,
            "state_path": str(self.paths.state_path),
            **state.to_json(),
        }

    def read_state(self) -> ServerState | None:
        """Read the persisted managed server state if it is valid.

        Returns:
            Persisted state, or None when absent or invalid.

        """
        path = self.paths.state_path
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            return ServerState.from_json(raw)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def wait_for_health(self, state: ServerState, *, timeout: float) -> bool:
        """Poll /healthz until the managed server is healthy or exits.

        Returns:
            True when /healthz becomes reachable before timeout.

        """
        deadline = time.monotonic() + timeout
        health_url = f"{state.base_url}/healthz"
        while time.monotonic() < deadline:
            if self.http_probe.reachable(health_url, timeout=0.5):
                return True
            if not self.process_ops.is_running(state.pid):
                return False
            time.sleep(self.poll_interval)
        return False

    def tail_logs(self, *, tail: int) -> tuple[Path, list[str]]:
        """Return the configured log path and the last requested log lines.

        Returns:
            Log path and up to tail lines.

        """
        log_path = self.paths.log_path
        if not log_path.exists():
            return log_path, []
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return log_path, lines[-tail:]

    def _write_state(self, state: ServerState) -> None:
        self.paths.state_path.write_text(
            json.dumps(state.to_json(), indent=2) + "\n",
            encoding="utf-8",
        )

    def _cleanup_failed_start(self, state: ServerState) -> None:
        with suppress(OSError):
            self.process_ops.terminate(state.pid)
        self.paths.state_path.unlink(missing_ok=True)

    def _wait_for_exit(self, pid: int, *, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.process_ops.is_running(pid):
                return True
            time.sleep(self.poll_interval)
        return False

    @staticmethod
    def _port_in_use(host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex((host, port)) == 0
