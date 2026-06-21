from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        """Build managed server state from persisted JSON."""
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
        """Serialize managed server state to JSON-compatible values."""
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
