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
from acodex.http.mcp.constants import MCP_PROTOCOL_VERSION

pytestmark = [
    pytest.mark.real_integration,
    pytest.mark.filterwarnings(
        "ignore:'asyncio\\.iscoroutinefunction' is deprecated and slated for removal in Python 3\\.16:DeprecationWarning",
    ),
]

_ENABLE_ENV = "ACODEX_RUN_REAL_INTEGRATION"
_LOCAL_HOST = "127.0.0.1"
_LIST_PROJECTS_TOOL = "codex_app.list_projects"
_LIST_THREADS_TOOL = "codex_app.list_threads"
_READ_THREAD_TOOL = "codex_app.read_thread"
_WORKSPACE_DEPENDENCIES_TOOL = "codex_app.load_workspace_dependencies"
_READ_ONLY_TOOL_NAMES = frozenset((
    _LIST_PROJECTS_TOOL,
    _LIST_THREADS_TOOL,
    _READ_THREAD_TOOL,
    _WORKSPACE_DEPENDENCIES_TOOL,
))


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


def test_mcp_tools_list_returns_live_read_only_tools(mcp_endpoint: str) -> None:
    initialize_response = _post_jsonrpc(
        mcp_endpoint,
        _jsonrpc_request(
            "initialize",
            request_id="initialize",
            params={
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "acodex-e2e", "version": "0"},
            },
        ),
    )
    initialize_result = _response_result(initialize_response)
    assert initialize_result["protocolVersion"] == MCP_PROTOCOL_VERSION

    tools_response = _post_jsonrpc(
        mcp_endpoint,
        _jsonrpc_request("tools/list", request_id="tools-list"),
    )
    tools = _tools_from_response(tools_response)
    tool_names = {tool["name"] for tool in tools if isinstance(tool.get("name"), str)}
    assert tool_names >= _READ_ONLY_TOOL_NAMES


def test_mcp_tools_call_read_only_tools(mcp_endpoint: str) -> None:
    list_threads_payload = _json_tool_payload(
        mcp_endpoint,
        name=_LIST_THREADS_TOOL,
        arguments={"limit": 1},
    )
    assert list_threads_payload["schemaVersion"] == 1
    assert list_threads_payload["query"] is None
    assert isinstance(list_threads_payload["threads"], list)
    assert list_threads_payload["threads"], "live Codex list_threads returned no threads"

    thread = list_threads_payload["threads"][0]
    assert isinstance(thread["id"], str)
    assert thread["id"]
    assert isinstance(thread["hostId"], str)
    assert isinstance(thread["title"], str)

    list_projects_payload = _json_tool_payload(
        mcp_endpoint,
        name=_LIST_PROJECTS_TOOL,
        arguments={},
    )
    assert list_projects_payload["schemaVersion"] == 1
    assert isinstance(list_projects_payload["projects"], list)

    workspace_text = _tool_text(
        mcp_endpoint,
        name=_WORKSPACE_DEPENDENCIES_TOOL,
        arguments={},
    )
    assert "Workspace dependencies" in workspace_text

    read_thread_payload = _json_tool_payload(
        mcp_endpoint,
        name=_READ_THREAD_TOOL,
        arguments={
            "threadId": thread["id"],
            "hostId": thread["hostId"],
            "turnLimit": 1,
            "includeOutputs": False,
        },
    )
    assert read_thread_payload["schemaVersion"] == 1
    assert read_thread_payload["thread"]["id"] == thread["id"]
    assert isinstance(read_thread_payload["turns"], list)


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


def _jsonrpc_request(
    method: str,
    *,
    request_id: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return payload


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


def _response_result(response: dict[str, Any]) -> dict[str, Any]:
    assert "error" not in response, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def _tools_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    result = _response_result(response)
    tools = result["tools"]
    assert isinstance(tools, list)
    assert all(isinstance(tool, dict) for tool in tools)
    return tools


def _tool_result(
    url: str,
    *,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    response = _post_jsonrpc(
        url,
        _jsonrpc_request(
            "tools/call",
            request_id=name,
            params={
                "name": name,
                "arguments": arguments,
            },
        ),
    )
    result = _response_result(response)
    assert result["isError"] is False, result
    return result


def _tool_text(url: str, *, name: str, arguments: dict[str, Any]) -> str:
    result = _tool_result(url, name=name, arguments=arguments)
    content = result["content"]
    assert isinstance(content, list)
    texts = [
        item["text"]
        for item in content
        if (
            isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        )
    ]
    assert texts, result
    return "\n".join(texts)


def _json_tool_payload(
    url: str,
    *,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    payload = json.loads(_tool_text(url, name=name, arguments=arguments))
    assert isinstance(payload, dict)
    return payload
