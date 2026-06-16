from __future__ import annotations

import asyncio
import json

import pytest

from acodex import (
    CodexAppCdpError,
    CodexAppCdpEvaluationError,
    CodexAppCdpProtocolError,
    JsonObject,
    parse_runtime_evaluate_response,
)
from acodex.core.asyncio.cdp import json_utils as cdp_json, runtime as cdp_runtime
from tests.cdp.helpers import FakeWebSocket


def test_parse_runtime_evaluate_response_returns_json_value() -> None:
    assert parse_runtime_evaluate_response(
        {"result": {"result": {"value": {"ok": True}}}},
    ) == {"ok": True}
    assert parse_runtime_evaluate_response({"result": {"result": {"type": "undefined"}}}) is None


RuntimeFailureCase = tuple[JsonObject, type[CodexAppCdpError], str]


@pytest.mark.parametrize(
    "case",
    [
        (
            {"error": {"message": "bad cdp"}},
            CodexAppCdpProtocolError,
            "bad cdp",
        ),
        (
            {
                "exceptionDetails": {
                    "text": "failed",
                    "exception": {"description": "boom"},
                },
            },
            CodexAppCdpEvaluationError,
            "boom",
        ),
        (
            {"exceptionDetails": {"text": "failed without exception object"}},
            CodexAppCdpEvaluationError,
            "failed without exception object",
        ),
        (
            {
                "result": {
                    "exceptionDetails": {
                        "text": "nested failed",
                        "exception": {"description": "nested boom"},
                    },
                },
            },
            CodexAppCdpEvaluationError,
            "nested boom",
        ),
        (
            {"result": {"exceptionDetails": {"text": "nested failed without exception object"}}},
            CodexAppCdpEvaluationError,
            "nested failed without exception object",
        ),
        (
            {"result": "missing"},
            CodexAppCdpProtocolError,
            "result object",
        ),
        (
            {"result": {"result": "missing"}},
            CodexAppCdpProtocolError,
            "remote result object",
        ),
        (
            {"result": {"result": {"description": "not serializable"}}},
            CodexAppCdpProtocolError,
            "not serializable",
        ),
    ],
)
def test_parse_runtime_evaluate_response_rejects_failures(
    case: RuntimeFailureCase,
) -> None:
    response, error_type, match = case
    with pytest.raises(error_type, match=match):
        parse_runtime_evaluate_response(response)


def test_cdp_runtime_connection_evaluates_and_ignores_notifications() -> None:
    websocket = FakeWebSocket(
        incoming=[
            json.dumps({"method": "Runtime.consoleAPICalled"}),
            json.dumps({"id": 1, "result": {"result": {"value": "ok"}}}).encode(),
        ],
    )
    runtime = cdp_runtime._CdpRuntimeConnection(websocket, timeout=0.1)

    assert asyncio.run(runtime.evaluate("1 + 1")) == "ok"
    asyncio.run(runtime.close())

    sent = json.loads(websocket.sent[0])
    assert sent == {
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {
            "expression": "1 + 1",
            "awaitPromise": True,
            "returnByValue": True,
        },
    }
    assert websocket.closed


def test_default_websocket_connector_uses_websockets_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    websocket = FakeWebSocket(
        incoming=[json.dumps({"id": 1, "result": {"result": {"value": "ok"}}})],
    )

    class FakeWebsocketsModule:
        @staticmethod
        async def connect(uri: str, *, max_size: int | None) -> FakeWebSocket:
            await asyncio.sleep(0)
            assert uri == "ws://target"
            assert max_size is None
            return websocket

    monkeypatch.setattr(cdp_runtime, "import_module", lambda _name: FakeWebsocketsModule())

    runtime = asyncio.run(cdp_runtime.connect_websocket_runtime("ws://target"))

    assert asyncio.run(runtime.evaluate("ok")) == "ok"


def test_json_decoding_rejects_non_object_and_non_json_values() -> None:
    with pytest.raises(CodexAppCdpProtocolError, match="JSON object"):
        cdp_json.decode_json_object("[]")
    with pytest.raises(CodexAppCdpProtocolError, match="keys"):
        cdp_json.ensure_json_value({1: "bad"})
    with pytest.raises(CodexAppCdpProtocolError, match="Unsupported"):
        cdp_json.ensure_json_value(object())
