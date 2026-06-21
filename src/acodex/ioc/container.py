from __future__ import annotations

from functools import cache

from diwire import Container, Scope

from acodex.cli.tools import (
    ManagedMCPToolsClientProvider,
    MCPToolsClientFactory,
    ToolArgumentsParser,
    ToolsCommand,
    ToolsPresenter,
    _build_server_manager,
)
from acodex.config import load_config
from acodex.core.codex_app.bridge import CodexAppBridge
from acodex.core.codex_app.cdp import CodexCDPClient
from acodex.http.mcp.handler import MCPRequestsHandler


def get_cli_container() -> Container:
    container = Container()

    _register_cli_dependencies(container)

    return container


@cache
def get_container() -> Container:
    container = Container()

    _register_http_dependencies(container)

    return container


def _register_cli_dependencies(container: Container) -> None:
    container.add_factory(_build_server_manager)
    container.add(MCPToolsClientFactory)
    container.add(ManagedMCPToolsClientProvider, scope=Scope.REQUEST)
    container.add(ToolArgumentsParser)
    container.add_factory(_build_tools_presenter, provides=ToolsPresenter, scope=Scope.REQUEST)
    container.add(ToolsCommand, scope=Scope.REQUEST)


def _build_tools_presenter() -> ToolsPresenter:
    return ToolsPresenter()


def _register_http_dependencies(container: Container) -> None:
    config = load_config()
    container.add_instance(config.to_cdp_settings())
    container.add(CodexCDPClient)
    container.add_instance(config.to_bridge_settings())
    container.add(CodexAppBridge)
    container.add(MCPRequestsHandler)
