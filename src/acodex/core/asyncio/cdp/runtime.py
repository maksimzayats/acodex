from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Mapping
from importlib import import_module
from typing import Any, NoReturn

from typing_extensions import override

from acodex.core.asyncio.cdp.errors import CodexAppCdpEvaluationError, CodexAppCdpProtocolError
from acodex.core.asyncio.cdp.json_utils import decode_json_object, dump_json
from acodex.core.asyncio.cdp.settings import DEFAULT_CDP_RUNTIME_TIMEOUT
from acodex.core.asyncio.cdp.types import JsonObject, JsonValue


class CdpRuntime(ABC):
    @abstractmethod
    async def evaluate(self, expression: str) -> JsonValue:
        """Evaluate a JavaScript expression through CDP Runtime.evaluate.

        Returns:
            The JSON-serializable value returned by the browser.

        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close the underlying runtime connection."""
        raise NotImplementedError


class CdpWebSocket(ABC):
    @abstractmethod
    async def send(self, message: str) -> None:
        """Send one serialized CDP websocket message."""
        raise NotImplementedError

    @abstractmethod
    async def recv(self) -> str | bytes:
        """Receive one raw CDP websocket message."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close the websocket connection."""
        raise NotImplementedError


class WrappedCdpWebSocket(CdpWebSocket):
    def __init__(self, websocket: Any) -> None:
        # websockets is imported dynamically so tests can replace the client module.
        self._websocket = websocket

    @override
    async def send(self, message: str) -> None:
        """Send one serialized CDP websocket message."""
        await self._websocket.send(message)

    @override
    async def recv(self) -> str | bytes:
        """Receive one raw CDP websocket message.

        Returns:
            The raw websocket message.

        Raises:
            CodexAppCdpProtocolError: If the message is not text or bytes.

        """
        message = await self._websocket.recv()
        if not isinstance(message, str | bytes):
            raise CodexAppCdpProtocolError("CDP websocket message must be text or bytes")
        return message

    @override
    async def close(self) -> None:
        """Close the websocket connection."""
        await self._websocket.close()


class CdpWebSocketConnector(ABC):
    @abstractmethod
    async def connect(self, websocket_url: str) -> CdpWebSocket:
        """Open a websocket connection to a CDP page target.

        Returns:
            A websocket wrapper for sending and receiving CDP messages.

        """
        raise NotImplementedError


class WebsocketsCdpWebSocketConnector(CdpWebSocketConnector):
    @override
    async def connect(self, websocket_url: str) -> CdpWebSocket:
        """Open a websocket connection to a CDP page target.

        Returns:
            A websocket wrapper for sending and receiving CDP messages.

        """
        client_module = import_module("websockets.asyncio.client")
        websocket = await client_module.connect(websocket_url, max_size=None)
        return WrappedCdpWebSocket(websocket)


class CdpRuntimeConnection(CdpRuntime):
    def __init__(
        self,
        websocket: CdpWebSocket,
        *,
        timeout: float = DEFAULT_CDP_RUNTIME_TIMEOUT,
    ) -> None:
        self._websocket = websocket
        self._timeout = timeout
        self._next_request_id = 1

    @override
    async def evaluate(self, expression: str) -> JsonValue:
        """Evaluate a JavaScript expression through CDP Runtime.evaluate.

        Returns:
            The JSON-serializable value returned by the browser.

        """
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

    @override
    async def close(self) -> None:
        """Close the underlying runtime connection."""
        await self._websocket.close()


class CdpRuntimeConnector(ABC):
    @abstractmethod
    async def connect(
        self,
        websocket_url: str,
        *,
        runtime_timeout: float = DEFAULT_CDP_RUNTIME_TIMEOUT,
    ) -> CdpRuntime:
        """Connect to a CDP page target and return a Runtime evaluator.

        Returns:
            A connected CDP runtime evaluator.

        """
        raise NotImplementedError


class WebsocketCdpRuntimeConnector(CdpRuntimeConnector):
    def __init__(self, websocket_connector: CdpWebSocketConnector | None = None) -> None:
        self._websocket_connector = websocket_connector or WebsocketsCdpWebSocketConnector()

    @override
    async def connect(
        self,
        websocket_url: str,
        *,
        runtime_timeout: float = DEFAULT_CDP_RUNTIME_TIMEOUT,
    ) -> CdpRuntime:
        """Connect to a CDP page target and return a Runtime evaluator.

        Returns:
            A connected CDP runtime evaluator.

        """
        websocket = await self._websocket_connector.connect(websocket_url)
        return CdpRuntimeConnection(websocket, timeout=runtime_timeout)


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
