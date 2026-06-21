from __future__ import annotations

from functools import cache

from diwire import Container

from acodex.config import load_config
from acodex.core.codex_app.bridge import CodexAppBridge
from acodex.core.codex_app.cdp import CodexCDPClient
from acodex.http.mcp.handler import MCPRequestsHandler


@cache
def get_container() -> Container:
    container = Container()

    _register_http_dependencies(container)

    return container


def _register_http_dependencies(container: Container) -> None:
    config = load_config()
    container.add_instance(config.to_cdp_settings())
    container.add(CodexCDPClient)
    container.add_instance(config.to_bridge_settings())
    container.add(CodexAppBridge)
    container.add(MCPRequestsHandler)
