from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, NoReturn, cast
from urllib import error as url_error, request as url_request


class MCPToolClientError(RuntimeError):
    """Raised when an MCP tool request cannot be completed."""


class MCPToolJSONRPCError(MCPToolClientError):
    """Raised when the MCP server returns a JSON-RPC error."""

    def __init__(self, *, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.data = data
        super().__init__(message)


@dataclass(kw_only=True, slots=True)
class MCPToolsClient:
    mcp_url: str
    timeout: float = 30.0
    _opener: Callable[..., Any] = url_request.urlopen  # noqa: S310 - caller supplies local MCP URL.
    _request_number: int = field(default=0, init=False)

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool descriptors exposed by the server.

        Returns:
            MCP tool descriptor objects.

        Raises:
            MCPToolClientError: If the server cannot be reached or returns invalid data.

        """
        result = self._request("tools/list")
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise MCPToolClientError("MCP tools/list result.tools must be an array")

        validated: list[dict[str, Any]] = []
        tool_payloads = cast("list[Any]", tools)  # type: ignore[redundant-cast]
        for tool in tool_payloads:
            if not isinstance(tool, dict):
                raise MCPToolClientError("MCP tools/list result.tools must contain objects")
            validated.append(cast("dict[str, Any]", tool))
        return validated

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP tool by name with JSON-object arguments.

        Returns:
            Normalized MCP tool result.

        """
        return self._request(
            "tools/call",
            params={
                "name": name,
                "arguments": arguments,
            },
        )

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self._jsonrpc_payload(method=method, params=params)
        request = url_request.Request(  # noqa: S310 - URL comes from local managed server state.
            self.mcp_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw_response = response.read().decode("utf-8")
        except (OSError, url_error.URLError) as exc:
            raise MCPToolClientError(
                f"Could not reach MCP server at {self.mcp_url}: {exc}",
            ) from exc

        try:
            response_payload = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise MCPToolClientError("MCP server returned invalid JSON") from exc

        if not isinstance(response_payload, dict):
            raise MCPToolClientError("MCP response must be a JSON object")
        typed_response = cast("dict[str, Any]", response_payload)

        if typed_response.get("error") is not None:
            _raise_jsonrpc_error(typed_response["error"])

        result = typed_response.get("result")
        if not isinstance(result, dict):
            raise MCPToolClientError("MCP response result must be an object")
        return cast("dict[str, Any]", result)

    def _jsonrpc_payload(
        self,
        *,
        method: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self._request_number += 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": f"acodex-tools-{self._request_number}",
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        return payload


def _raise_jsonrpc_error(error: Any) -> NoReturn:
    if not isinstance(error, dict):
        raise MCPToolClientError("MCP JSON-RPC error must be an object")
    error_payload = cast("dict[str, Any]", error)

    code = error_payload.get("code")
    message = error_payload.get("message")
    if not isinstance(code, int) or not isinstance(message, str):
        raise MCPToolClientError("MCP JSON-RPC error must include code and message")

    raise MCPToolJSONRPCError(
        code=code,
        message=message,
        data=error_payload.get("data"),
    )
