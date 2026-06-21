from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI

from acodex.core.codex_app.cdp import CodexCDPClient
from acodex.http import app as app_module


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeCDP:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeContainer:
    def __init__(self, cdp: FakeCDP) -> None:
        self.cdp = cdp

    def resolve(self, dependency: type[Any]) -> Any:
        assert dependency is CodexCDPClient
        return self.cdp


def test_fastapi_factory_includes_mcp_router() -> None:
    app = app_module.FastAPIFactory()()
    assert isinstance(app, FastAPI)
    assert any(
        getattr(route, "original_router", None) is app_module.mcp_router for route in app.routes
    )


def test_lifespan_closes_cdp(monkeypatch: Any) -> None:
    async def scenario() -> None:
        cdp = FakeCDP()
        monkeypatch.setattr(app_module, "container", FakeContainer(cdp))
        async with app_module.lifespan(FastAPI()):
            assert not cdp.closed
        assert cdp.closed

    run(scenario())
