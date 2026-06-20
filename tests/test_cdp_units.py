from __future__ import annotations

import asyncio
import json
import urllib.error
from typing import Any, cast

import pytest
from typing_extensions import Self

from acodex.core.codex_app import cdp as cdp_module
from acodex.core.codex_app.cdp import CodexCDPClient, CodexCDPError, CodexCDPSettings


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeWebSocket:
    def __init__(self, client: CodexCDPClient | None = None) -> None:
        self.client = client
        self.sent: list[str] = []
        self.closed = False
        self.fail_send = False
        self.error_response = False

    async def send(self, payload: str) -> None:
        self.sent.append(payload)
        if self.fail_send:
            raise OSError("send failed")
        if self.client is not None:
            message = json.loads(payload)
            future = self.client._pending[message["id"]]
            if self.error_response:
                future.set_result({
                    "id": message["id"],
                    "error": {"message": "bad"},
                })
                return
            future.set_result({"id": message["id"], "result": {"ok": True}})

    async def close(self) -> None:
        self.closed = True


class IterableWebSocket:
    def __init__(self, messages: list[str | bytes], *, fail: bool = False) -> None:
        self.messages = messages
        self.fail = fail

    def __aiter__(self) -> IterableWebSocket:
        return self

    async def __anext__(self) -> str | bytes:
        if self.messages:
            return self.messages.pop(0)
        if self.fail:
            self.fail = False
            raise OSError("closed")
        raise StopAsyncIteration


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_settings_base_url() -> None:
    assert CodexCDPSettings(host="localhost", port=1234).base_url == "http://localhost:1234"


def test_command_sends_cdp_payload_and_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexCDPClient(_settings=CodexCDPSettings(request_timeout=0.1))
    ws = FakeWebSocket(client)
    client._ws = ws

    async def ensure_connected(self: CodexCDPClient) -> None:
        await asyncio.sleep(0)
        assert self is client

    monkeypatch.setattr(CodexCDPClient, "_ensure_connected", ensure_connected)

    assert run(client.command("Runtime.evaluate", {"expression": "1"})) == {"ok": True}
    assert json.loads(ws.sent[0]) == {
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {"expression": "1"},
    }

    assert run(client.command("Page.getResourceTree")) == {"ok": True}
    assert json.loads(ws.sent[1]) == {"id": 2, "method": "Page.getResourceTree"}


def test_command_errors_and_cleans_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexCDPClient(_settings=CodexCDPSettings(request_timeout=0.1))

    async def ensure_without_ws(self: CodexCDPClient) -> None:
        await asyncio.sleep(0)
        assert self is client
        self._ws = None

    monkeypatch.setattr(CodexCDPClient, "_ensure_connected", ensure_without_ws)
    with pytest.raises(CodexCDPError, match="not connected"):
        run(client.command("Runtime.evaluate"))

    ws = FakeWebSocket(client)
    ws.fail_send = True
    client._ws = ws

    async def ensure_with_ws(self: CodexCDPClient) -> None:
        await asyncio.sleep(0)
        assert self is client

    monkeypatch.setattr(CodexCDPClient, "_ensure_connected", ensure_with_ws)
    with pytest.raises(OSError, match="send failed"):
        run(client.command("Runtime.evaluate"))
    assert client._pending == {}

    ws.fail_send = False
    ws.error_response = True
    with pytest.raises(CodexCDPError, match=r"CDP Runtime\.evaluate failed"):
        run(client.command("Runtime.evaluate"))


def test_evaluate_resource_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexCDPClient(_settings=CodexCDPSettings())
    results = iter(
        [
            {
                "result": {
                    "value": {"answer": 1},
                },
            },
            {"exceptionDetails": {"text": "failed", "exception": {"description": "details"}}},
            {"exceptionDetails": {"text": "failed"}},
            {"result": {"subtype": "null"}},
            {"result": {"description": "remote object"}},
            {"result": {}},
            {"result": "raw"},
            {"frameTree": {"frame": {"id": "root"}}},
            {"base64Encoded": True},
            {"content": 1},
            {"content": "text"},
        ],
    )

    async def command(  # noqa: PLR0917
        self: CodexCDPClient,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        await asyncio.sleep(0)
        assert self is client
        if method == "Runtime.evaluate":
            assert params
            assert params["returnByValue"] is True
        return next(results)

    monkeypatch.setattr(CodexCDPClient, "command", command)

    assert run(client.evaluate("1")) == {"answer": 1}
    with pytest.raises(CodexCDPError, match="failed: details"):
        run(client.evaluate("bad"))
    with pytest.raises(CodexCDPError, match="failed"):
        run(client.evaluate("bad"))
    assert run(client.evaluate("null")) is None
    assert run(client.evaluate("object")) == "remote object"
    assert run(client.evaluate("object")) == {}
    assert run(client.evaluate("raw")) == "raw"
    assert run(client.resource_tree()) == {"frameTree": {"frame": {"id": "root"}}}
    with pytest.raises(CodexCDPError, match="base64 encoded"):
        run(client.resource_content("frame", "app://-/asset.js"))
    assert not run(client.resource_content("frame", "app://-/asset.js"))
    assert run(client.resource_content("frame", "app://-/asset.js")) == "text"


def test_recv_loop_and_close_fail_pending() -> None:
    async def scenario() -> None:
        client = CodexCDPClient(_settings=CodexCDPSettings())
        loop = asyncio.get_running_loop()

        future = loop.create_future()
        client._pending[1] = future
        client._handle_recv_message("not json")
        client._handle_recv_message(json.dumps(["not", "a dict"]))
        client._handle_recv_message(json.dumps({"id": "not-int"}))
        client._handle_recv_message(json.dumps({"id": 2}))
        client._handle_recv_message(json.dumps({"id": 1, "result": {"ok": True}}))
        assert future.result() == {"id": 1, "result": {"ok": True}}

        pending = loop.create_future()
        client._pending[3] = pending
        client._fail_pending(CodexCDPError("failed"))
        assert client._pending == {}
        assert isinstance(pending.exception(), CodexCDPError)

        await client._recv_loop()

        client._pending[4] = loop.create_future()
        client._ws = IterableWebSocket([json.dumps({"id": 4, "result": {"ok": True}})], fail=True)
        await client._recv_loop()
        assert client._ws is None

        close_ws = FakeWebSocket()  # type: ignore[unreachable]
        client._ws = close_ws
        client._pending[5] = loop.create_future()
        client._recv_task = asyncio.create_task(asyncio.sleep(10))
        await client.close()
        assert close_ws.closed
        assert client._ws is None
        assert client._recv_task is None

        done = loop.create_future()
        done.set_result({})
        pending = loop.create_future()
        client._pending[6] = done
        client._pending[7] = pending
        client._fail_pending(CodexCDPError("second failure"))
        assert done.result() == {}
        assert isinstance(pending.exception(), CodexCDPError)

        await client.close()

    run(scenario())


def test_ensure_connected_uses_existing_or_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        client = CodexCDPClient(_settings=CodexCDPSettings(request_timeout=0.1))
        existing = FakeWebSocket()
        client._ws = existing
        await client._ensure_connected()
        assert client._ws is existing

        client._ws = None
        monkeypatch.setattr(
            CodexCDPClient,
            "_find_codex_target",
            lambda _self: {"webSocketDebuggerUrl": ""},
        )
        with pytest.raises(CodexCDPError, match="websocket URL"):
            await client._ensure_connected()

        connected = IterableWebSocket([])

        async def connect(url: str, *, open_timeout: float) -> IterableWebSocket:
            await asyncio.sleep(0)
            assert url == "ws://target"
            assert open_timeout == pytest.approx(0.1)
            return connected

        monkeypatch.setattr(
            CodexCDPClient,
            "_find_codex_target",
            lambda _self: {"webSocketDebuggerUrl": "ws://target"},
        )
        monkeypatch.setattr(cdp_module.websockets, "connect", connect)
        await client._ensure_connected()
        assert client._ws is connected
        assert client._recv_task is not None  # type: ignore[unreachable]
        await client._recv_task
        assert client._ws is None

    run(scenario())


def test_find_codex_target(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexCDPClient(_settings=CodexCDPSettings(host="host", port=1, request_timeout=0.1))
    payloads: list[Any] = [
        urllib.error.URLError("no server"),
        [],
        ["bad"],
        [{"type": "page", "url": "app://-/index.html", "webSocketDebuggerUrl": "ws://app"}],
        [
            {"type": "worker", "url": "app://-/worker.js"},
            {"type": "page", "url": "https://example.com", "webSocketDebuggerUrl": "ws://page"},
        ],
        [{"type": "worker", "url": "https://example.com"}],
    ]

    def urlopen(url: str, *, timeout: float) -> FakeResponse:
        assert url == "http://host:1/json/list"
        assert timeout == pytest.approx(0.1)
        payload = cast("Any", payloads.pop(0))
        if isinstance(payload, BaseException):
            raise payload
        return FakeResponse(payload)

    monkeypatch.setattr(cdp_module.urllib.request, "urlopen", urlopen)

    with pytest.raises(CodexCDPError, match="Could not reach Codex CDP"):
        client._find_codex_target()
    with pytest.raises(CodexCDPError, match="No CDP targets found"):
        client._find_codex_target()
    with pytest.raises(CodexCDPError, match="No page target found"):
        client._find_codex_target()
    assert client._find_codex_target()["webSocketDebuggerUrl"] == "ws://app"
    assert client._find_codex_target()["webSocketDebuggerUrl"] == "ws://page"
    with pytest.raises(CodexCDPError, match="No page target found"):
        client._find_codex_target()
