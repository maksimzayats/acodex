from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Request

ALLOWED_ORIGIN_HOSTS = frozenset(("127.0.0.1", "localhost", "::1"))


@dataclass(frozen=True, slots=True)
class OriginPolicy:
    """Validate browser origins allowed to call the local MCP endpoint."""

    allowed_hosts: frozenset[str] = ALLOWED_ORIGIN_HOSTS

    def allows(self, request: Request) -> bool:
        """Return whether the request origin is allowed."""
        origin = request.headers.get("Origin")
        if not origin:
            return True
        try:
            parsed_origin = urlparse(origin)
        except ValueError:
            return False
        return parsed_origin.hostname in self.allowed_hosts
