from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Mapping
from importlib import import_module
from typing import NoReturn, Protocol, cast

from acodex.asyncio.cdp.errors import CodexAppCdpEvaluationError, CodexAppCdpProtocolError
from acodex.asyncio.cdp.json_utils import decode_json_object, dump_json
from acodex.asyncio.cdp.settings import DEFAULT_CDP_RUNTIME_TIMEOUT
from acodex.asyncio.cdp.types import JsonObject, JsonValue


class CdpRuntimeEvaluator(Protocol):
    async def evaluate(self, expression: str) -> JsonValue:
        """Evaluate a JavaScript expression through CDP Runtime.evaluate.

        Returns:
            The JSON-serializable value returned by the browser.

        """

    async def close(self) -> None:
        """Close the underlying runtime connection."""


class _CdpWebSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...

    async def close(self) -> None: ...


class _WebSocketConnect(Protocol):
    def __call__(self, uri: str, *, max_size: int | None) -> Awaitable[_CdpWebSocket]: ...


class _CdpRuntimeConnection:
    def __init__(
        self,
        websocket: _CdpWebSocket,
        *,
        timeout: float = DEFAULT_CDP_RUNTIME_TIMEOUT,
    ) -> None:
        self._websocket = websocket
        self._timeout = timeout
        self._next_request_id = 1

    async def evaluate(self, expression: str) -> JsonValue:
        request_id = self._next_request_id
        self._next_request_id += 1
        request: JsonObject = {
            "id": request_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        }
        await self._websocket.send(dump_json(request))

        while True:
            message = await asyncio.wait_for(self._websocket.recv(), timeout=self._timeout)
            response = decode_json_object(message)
            if response.get("id") == request_id:
                return parse_runtime_evaluate_response(response)

    async def close(self) -> None:
        await self._websocket.close()


async def connect_websocket_runtime(
    websocket_url: str,
    *,
    runtime_timeout: float = DEFAULT_CDP_RUNTIME_TIMEOUT,
) -> CdpRuntimeEvaluator:
    client_module = import_module("websockets.asyncio.client")
    connect = cast("_WebSocketConnect", client_module.connect)
    websocket = await connect(websocket_url, max_size=None)
    return _CdpRuntimeConnection(websocket, timeout=runtime_timeout)


def parse_runtime_evaluate_response(response: JsonObject) -> JsonValue:
    error = response.get("error")
    if isinstance(error, dict):
        message = _get_string(error, "message") or "CDP Runtime.evaluate returned an error"
        raise CodexAppCdpProtocolError(message)

    exception_details = response.get("exceptionDetails")
    if isinstance(exception_details, dict):
        _raise_evaluation_error(exception_details)

    result = response.get("result")
    if not isinstance(result, dict):
        raise CodexAppCdpProtocolError("CDP response is missing a result object")

    nested_exception_details = result.get("exceptionDetails")
    if isinstance(nested_exception_details, dict):
        _raise_evaluation_error(nested_exception_details)

    remote_result = result.get("result")
    if not isinstance(remote_result, dict):
        raise CodexAppCdpProtocolError("CDP response is missing a remote result object")

    if "value" in remote_result:
        return remote_result["value"]
    if remote_result.get("type") == "undefined":
        return None

    description = (
        _get_string(remote_result, "description") or "Runtime.evaluate did not return a JSON value"
    )
    raise CodexAppCdpProtocolError(description)


def _get_string(mapping: Mapping[str, JsonValue], key: str) -> str | None:
    value = mapping.get(key)
    return value if isinstance(value, str) else None


def _raise_evaluation_error(exception_details: Mapping[str, JsonValue]) -> NoReturn:
    exception = exception_details.get("exception")
    if isinstance(exception, dict):
        description = _get_string(exception, "description") or _get_string(exception, "value")
    else:
        description = None
    text = _get_string(exception_details, "text")
    raise CodexAppCdpEvaluationError(description or text or "Runtime.evaluate failed")
