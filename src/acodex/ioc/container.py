from __future__ import annotations

from functools import cache

from diwire import Container

from acodex.core.codex_app.bridge import CodexAppBridge, CodexAppBridgeSettings
from acodex.core.codex_app.cdp import CodexCDPClient, CodexCDPSettings
from acodex.http.mcp.handler import MCPRequestsHandler


@cache
def get_container() -> Container:
    container = Container()

    _register_dependencies(container)

    return container


def _register_dependencies(container: Container) -> None:
    container.add_instance(CodexCDPSettings())
    container.add(CodexCDPClient)
    container.add_instance(CodexAppBridgeSettings())
    container.add(CodexAppBridge)
    container.add(MCPRequestsHandler)
