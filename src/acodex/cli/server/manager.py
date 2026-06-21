from __future__ import annotations

import sys
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from acodex.cli.server.models import ServerError, ServerPaths, ServerState
from acodex.cli.server.probe import HttpProbe, SocketPortChecker
from acodex.cli.server.process import ProcessOps
from acodex.cli.server.state_store import ServerStateStore
from acodex.config import AcodexConfig, config_root

HEALTH_PATH = "/healthz"
MCP_PATH = "/mcp"
SERVER_MODULE = "acodex.http.app:app"
STARTUP_TIMEOUT = 5.0
STOP_TIMEOUT = 5.0
KILL_TIMEOUT = 2.0
HEALTH_PROBE_TIMEOUT = 0.5
STATUS_PROBE_TIMEOUT = 1.0


@dataclass(kw_only=True, slots=True)
class ServerManager:
    """Control the managed acodex HTTP server process."""

    config_path: Path | None = None
    process_ops: ProcessOps = field(default_factory=ProcessOps)
    http_probe: HttpProbe = field(default_factory=HttpProbe)
    port_checker: SocketPortChecker = field(default_factory=SocketPortChecker)
    state_store: ServerStateStore = field(default_factory=ServerStateStore)
    poll_interval: float = 0.1

    @property
    def paths(self) -> ServerPaths:
        """Return runtime paths derived from the effective config path."""
        root_path = config_root(self.config_path)
        return ServerPaths(
            state_path=root_path / "run" / "server.json",
            log_path=root_path / "logs" / "server.log",
        )

    def start(self, config: AcodexConfig) -> ServerState:
        """Start the managed uvicorn server and persist its state."""
        self._clear_stale_state()
        if self.port_checker.is_in_use(config.server.host, config.server.port):
            raise ServerError(
                "Port {}:{} is already in use".format(config.server.host, config.server.port),
            )

        paths = self.paths
        paths.state_path.parent.mkdir(parents=True, exist_ok=True)
        paths.log_path.parent.mkdir(parents=True, exist_ok=True)
        server_state = self._spawn_server(config, paths)
        self.state_store.write(paths.state_path, server_state)
        if self.wait_for_health(server_state, timeout=STARTUP_TIMEOUT):
            return server_state
        self._cleanup_failed_start(server_state)
        raise ServerError(f"Server did not become healthy. See logs at {paths.log_path}")

    def stop(self, *, force: bool) -> bool:
        """Stop the managed server if it is running."""
        server_state = self.read_state()
        if server_state is None:
            return False
        if not self.process_ops.is_running(server_state.pid):
            self.paths.state_path.unlink(missing_ok=True)
            return False

        self.process_ops.terminate(server_state.pid)
        if self._wait_for_exit(server_state.pid, timeout=STOP_TIMEOUT):
            self.paths.state_path.unlink(missing_ok=True)
            return True
        if not force:
            raise ServerError(
                f"Server PID {server_state.pid} did not exit; retry with --force",
            )
        self.process_ops.kill(server_state.pid)
        self._wait_for_exit(server_state.pid, timeout=KILL_TIMEOUT)
        self.paths.state_path.unlink(missing_ok=True)
        return True

    def status(self) -> dict[str, Any]:
        """Return current managed server status."""
        server_state = self.read_state()
        if server_state is None:
            return {"running": False, "managed": False, "state_path": str(self.paths.state_path)}
        running = self.process_ops.is_running(server_state.pid)
        healthy = running and self.http_probe.reachable(
            f"{server_state.base_url}{HEALTH_PATH}",
            timeout=STATUS_PROBE_TIMEOUT,
        )
        if not running:
            self.paths.state_path.unlink(missing_ok=True)
        return {
            "running": running,
            "managed": True,
            "healthy": healthy,
            "state_path": str(self.paths.state_path),
            **server_state.to_json(),
        }

    def read_state(self) -> ServerState | None:
        """Read the persisted managed server state if it is valid."""
        return self.state_store.read(self.paths.state_path)

    def wait_for_health(self, server_state: ServerState, *, timeout: float) -> bool:
        """Poll /healthz until the managed server is healthy or exits."""
        deadline = time.monotonic() + timeout
        health_url = f"{server_state.base_url}{HEALTH_PATH}"
        while time.monotonic() < deadline:
            if self.http_probe.reachable(health_url, timeout=HEALTH_PROBE_TIMEOUT):
                return True
            if not self.process_ops.is_running(server_state.pid):
                return False
            time.sleep(self.poll_interval)
        return False

    def tail_logs(self, *, tail: int) -> tuple[Path, list[str]]:
        """Return the configured log path and the last requested log lines."""
        log_path = self.paths.log_path
        if not log_path.exists():
            return log_path, []
        log_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return log_path, log_lines[-tail:]

    def _clear_stale_state(self) -> None:
        server_state = self.read_state()
        if server_state is None:
            return
        if self.process_ops.is_running(server_state.pid):
            raise ServerError(
                f"Managed server is already running at {server_state.base_url}",
            )
        self.paths.state_path.unlink(missing_ok=True)

    def _spawn_server(self, config: AcodexConfig, paths: ServerPaths) -> ServerState:
        base_url = "http://{}:{}".format(config.server.host, config.server.port)
        command = self._server_command(config)
        with paths.log_path.open("ab") as log_file:
            pid = self.process_ops.spawn(command, log_file)
        return ServerState(
            pid=pid,
            host=config.server.host,
            port=config.server.port,
            base_url=base_url,
            mcp_url=f"{base_url}{MCP_PATH}",
            started_at=time.time(),
            log_path=str(paths.log_path),
            command=command,
        )

    def _server_command(self, config: AcodexConfig) -> list[str]:
        return [
            sys.executable,
            "-m",
            "uvicorn",
            SERVER_MODULE,
            "--host",
            config.server.host,
            "--port",
            str(config.server.port),
        ]

    def _cleanup_failed_start(self, server_state: ServerState) -> None:
        with suppress(OSError):
            self.process_ops.terminate(server_state.pid)
        self.paths.state_path.unlink(missing_ok=True)

    def _wait_for_exit(self, pid: int, *, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.process_ops.is_running(pid):
                return True
            time.sleep(self.poll_interval)
        return False
