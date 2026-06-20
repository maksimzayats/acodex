from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn

from acodex.core.codex_app.cdp import CodexCDPSettings
from acodex.http.app import app

pytestmark = [
    pytest.mark.real_integration,
    pytest.mark.filterwarnings(
        "ignore:'asyncio\\.iscoroutinefunction' is deprecated and slated for removal in Python 3\\.16:DeprecationWarning",
    ),
]

_ENABLE_ENV = "ACODEX_RUN_REAL_INTEGRATION"
_LOCAL_HOST = "127.0.0.1"


@pytest.fixture(scope="module")
def mcp_endpoint() -> Iterator[str]:
    _skip_unless_real_integration_enabled()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((_LOCAL_HOST, 0))
    sock.listen(128)
    port = sock.getsockname()[1]

    config = uvicorn.Config(
        app,
        host=_LOCAL_HOST,
        port=port,
        lifespan="on",
        log_level="warning",
        ws="none",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        daemon=True,
        name="acodex-mcp-e2e-server",
    )
    thread.start()

    base_url = f"http://{_LOCAL_HOST}:{port}"
    try:
        _wait_for_server(base_url)
        yield f"{base_url}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            pytest.fail("Uvicorn MCP test server did not stop")


def test_mcp_tools_call_list_threads_returns_live_threads(mcp_endpoint: str) -> None:
    tools_response = _post_jsonrpc(
        mcp_endpoint,
        {
            "jsonrpc": "2.0",
            "id": "tools-list",
            "method": "tools/list",
        },
    )
    assert "error" not in tools_response, tools_response
    tools = tools_response["result"]["tools"]
    assert any(tool.get("name") == "codex_app.list_threads" for tool in tools)

    call_response = _post_jsonrpc(
        mcp_endpoint,
        {
            "jsonrpc": "2.0",
            "id": "list-threads",
            "method": "tools/call",
            "params": {
                "name": "codex_app.list_threads",
                "arguments": {"limit": 1},
            },
        },
    )

    assert "error" not in call_response, call_response
    result = call_response["result"]
    assert result["isError"] is False

    text = "\n".join(
        item["text"]
        for item in result["content"]
        if item.get("type") == "text" and isinstance(item.get("text"), str)
    )
    payload = json.loads(text)

    assert payload["schemaVersion"] == 1
    assert payload["query"] is None
    assert isinstance(payload["threads"], list)
    assert payload["threads"], "live Codex list_threads returned no threads"

    thread = payload["threads"][0]
    assert isinstance(thread["id"], str)
    assert thread["id"]
    assert isinstance(thread["hostId"], str)
    assert isinstance(thread["title"], str)


def _skip_unless_real_integration_enabled() -> None:
    if os.environ.get(_ENABLE_ENV, "").lower() not in {"1", "true", "yes", "on"}:
        pytest.skip(f"set {_ENABLE_ENV}=1 to run live Codex desktop MCP E2E tests")

    cdp_settings = CodexCDPSettings()
    try:
        _get_json(f"{cdp_settings.base_url}/json/list", timeout=cdp_settings.request_timeout)
    except (OSError, urllib.error.URLError) as exc:
        pytest.skip(f"live Codex CDP is unavailable at {cdp_settings.base_url}: {exc}")


def _wait_for_server(base_url: str) -> None:
    deadline = time.monotonic() + 10
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        ok, error = _try_get_json(f"{base_url}/healthz", timeout=0.5)
        if ok:
            return
        last_error = error
        time.sleep(0.05)
    pytest.fail(f"MCP test server did not start: {last_error!r}")


def _try_get_json(url: str, *, timeout: float) -> tuple[bool, BaseException | None]:
    try:
        _get_json(url, timeout=timeout)
    except (OSError, urllib.error.URLError) as exc:
        return False, exc
    else:
        return True, None


def _get_json(url: str, *, timeout: float) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _post_jsonrpc(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Origin": f"http://{_LOCAL_HOST}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        result = json.loads(response.read().decode("utf-8"))
    assert isinstance(result, dict)
    return result
