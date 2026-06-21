from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from acodex.core.codex_app.cdp import CodexCDPClient
from acodex.http.mcp.routes import mcp_router
from acodex.ioc.http import get_container

container = get_container()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    try:
        yield
    finally:
        cdp = container.resolve(CodexCDPClient)
        await cdp.close()


@dataclass(kw_only=True, slots=True)
class FastAPIFactory:
    def __call__(self) -> FastAPI:
        """Build the FastAPI application.

        Returns:
            The configured FastAPI application.

        """
        app = FastAPI(lifespan=lifespan)
        app.include_router(mcp_router)

        return app


app_factory = container.resolve(FastAPIFactory)
app = app_factory()
