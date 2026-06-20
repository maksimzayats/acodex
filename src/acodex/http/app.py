from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from acodex.http.mcp.routes import mcp_router
from acodex.ioc.container import get_container

container = get_container()


@dataclass(kw_only=True, slots=True)
class FastAPIFactory:
    def __call__(self) -> FastAPI:
        """Build the FastAPI application.

        Returns:
            The configured FastAPI application.

        """
        app = FastAPI()
        app.include_router(mcp_router)

        return app


app_factory = container.resolve(FastAPIFactory)
app = app_factory()
