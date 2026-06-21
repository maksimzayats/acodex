from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import cast

from diwire import Container, Scope

from acodex.cli.tools import (
    ManagedMCPToolsClientProvider,
    MCPToolsClientFactory,
    ServerManager,
    ToolArgumentsParser,
    ToolsCommand,
    ToolsPresenter,
)
from acodex.cli.tools.factories import build_server_manager, build_tools_client_factory


def get_cli_container() -> Container:
    container = Container()

    _register_cli_dependencies(container)

    return container


def get_container() -> Container:
    get_http_container = cast(
        Callable[[], Container],
        import_module("acodex.ioc.http").get_container,
    )
    return get_http_container()


def _register_cli_dependencies(container: Container) -> None:
    container.add_factory(build_server_manager, provides=ServerManager)
    container.add_factory(build_tools_client_factory, provides=MCPToolsClientFactory)
    container.add(ManagedMCPToolsClientProvider, scope=Scope.REQUEST)
    container.add(ToolArgumentsParser)
    container.add_factory(_build_tools_presenter, provides=ToolsPresenter, scope=Scope.REQUEST)
    container.add(ToolsCommand, scope=Scope.REQUEST)


def _build_tools_presenter() -> ToolsPresenter:
    return ToolsPresenter()
