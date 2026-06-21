from __future__ import annotations

from dataclasses import dataclass, field

from diwire import Injected

from acodex.cli.server import ServerError, ServerManager
from acodex.core.mcp_tools import MCPToolsClient

RUNNING_KEY = "running"
HEALTHY_KEY = "healthy"
MCP_URL_KEY = "mcp_url"


@dataclass(frozen=True, slots=True)
class MCPToolsClientFactory:
    """Create MCP tool clients for managed-server URLs."""

    client_class: type[MCPToolsClient] = field(default=MCPToolsClient)

    def create(self, *, mcp_url: str) -> MCPToolsClient:
        """Build an MCP tools client for the managed server URL."""
        return self.client_class(mcp_url=mcp_url)


@dataclass(frozen=True, kw_only=True, slots=True)
class ManagedMCPToolsClientProvider:
    """Validate managed server state before returning a tools client."""

    server_manager: Injected[ServerManager]
    client_factory: Injected[MCPToolsClientFactory]

    def create(self) -> MCPToolsClient:
        """Return an MCP tools client after validating managed server status.

        Raises:
            ServerError: If the managed server is stopped, unhealthy, or missing an MCP URL.

        """
        server_status = self.server_manager.status()
        if not server_status.get(RUNNING_KEY):
            raise ServerError("Managed server is not running. Start it with `acodex server start`.")
        if not server_status.get(HEALTHY_KEY):
            raise ServerError(
                "Managed server is not healthy. Check `acodex server logs --tail 50` or restart it.",
            )

        mcp_url = server_status.get(MCP_URL_KEY)
        if not isinstance(mcp_url, str) or not mcp_url:
            raise ServerError("Managed server status did not include an MCP URL. Restart it.")
        return self.client_factory.create(mcp_url=mcp_url)
