from __future__ import annotations

import json
import socket
from urllib import error as url_error, request as url_request

HTTP_OK = 200
HTTP_REDIRECT = 300
PORT_PROBE_TIMEOUT = 0.2


class HttpProbe:
    """Probe HTTP endpoints used by the managed server."""

    __slots__ = ()

    def reachable(self, url: str, *, timeout: float) -> bool:
        """Return whether an HTTP endpoint responds with a 2xx status."""
        try:
            with url_request.urlopen(url, timeout=timeout) as response:  # noqa: S310
                return HTTP_OK <= response.status < HTTP_REDIRECT
        except (OSError, url_error.URLError):
            return False

    def mcp_initialize(self, mcp_url: str, *, timeout: float) -> bool:
        """Run a minimal MCP initialize request against the HTTP server."""
        request = self._initialize_request(mcp_url)
        try:
            with url_request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return HTTP_OK <= response.status < HTTP_REDIRECT
        except (OSError, url_error.URLError):
            return False

    def _initialize_request(self, mcp_url: str) -> url_request.Request:
        return url_request.Request(  # noqa: S310
            mcp_url,
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "doctor",
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26"},
                },
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )


class SocketPortChecker:
    """Check whether a host/port pair accepts TCP connections."""

    __slots__ = ()

    def is_in_use(self, host: str, port: int) -> bool:
        """Return whether a TCP port is already in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(PORT_PROBE_TIMEOUT)
            return sock.connect_ex((host, port)) == 0
