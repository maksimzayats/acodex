import json

from diwire import resolver_context, Scope, Injected
from fastapi import APIRouter, Request, Response
from starlette import status

from acodex.core.codex_app.bridge import CodexAppBridge
from acodex.http.mcp.handler import MCPRequestsHandler, MCP_PROTOCOL_VERSION

mcp_router = APIRouter(tags=["MCP"])


@mcp_router.post("/mcp")
@resolver_context.inject(scope=Scope.REQUEST)
async def handle_mcp(
    request: Request,
    *,
    handler: Injected[MCPRequestsHandler],
) -> Response:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return Response(
            content=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                },
            ),
            status_code=status.HTTP_200_OK,
            headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
            media_type="application/json",
        )

    return Response(status_code=204)
