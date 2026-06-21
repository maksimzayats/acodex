from __future__ import annotations

from acodex.cli.server import ServerManager
from acodex.cli.tools.client_provider import MCPToolsClientFactory
from acodex.core.mcp_tools import MCPToolsClient


def build_server_manager() -> ServerManager:
    return ServerManager()


def build_tools_client_factory() -> MCPToolsClientFactory:
    return MCPToolsClientFactory(client_class=MCPToolsClient)
