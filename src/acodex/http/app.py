from fastapi import FastAPI

from acodex.http.mcp.routes import mcp_router

app = FastAPI()
app.include_router(mcp_router)
