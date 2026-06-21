from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from acodex.cli.server.models import ServerState


@dataclass(frozen=True, slots=True)
class ServerStateStore:
    """Read and write managed-server state files."""

    def read(self, state_path: Path) -> ServerState | None:
        """Read the persisted managed server state if it is valid."""
        if not state_path.exists():
            return None
        try:
            file_payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(file_payload, dict):
            return None
        return self._parse_state(cast("dict[str, object]", file_payload))

    def write(self, state_path: Path, server_state: ServerState) -> None:
        """Persist managed server state."""
        state_path.write_text(
            f"{json.dumps(server_state.to_json(), indent=2)}\n",
            encoding="utf-8",
        )

    def _parse_state(self, file_payload: dict[str, object]) -> ServerState | None:
        try:
            return ServerState.from_json(file_payload)
        except (KeyError, TypeError, ValueError):
            return None
