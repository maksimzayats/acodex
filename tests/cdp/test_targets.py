from __future__ import annotations

import asyncio

import pytest

from acodex.core.asyncio.cdp import targets as cdp_targets
from acodex.core.asyncio.cdp.errors import CodexAppCdpConnectionError, CodexAppCdpProtocolError
from acodex.core.asyncio.cdp.targets import (
    fetch_cdp_targets,
    parse_cdp_targets,
    select_codex_app_target,
)
from acodex.core.asyncio.cdp.types import CdpTarget
from tests.cdp.helpers import JsonServer


def test_parse_and_select_cdp_targets() -> None:
    targets = parse_cdp_targets(
        [
            "ignored",
            {
                "id": "devtools",
                "type": "other",
                "url": "devtools://devtools",
                "webSocketDebuggerUrl": "ws://devtools",
            },
            {
                "id": "fallback",
                "type": "page",
                "url": "app://-/other.html",
                "webSocketDebuggerUrl": "ws://fallback",
            },
            {
                "id": "exact",
                "type": "page",
                "url": "app://-/index.html",
                "webSocketDebuggerUrl": "ws://exact",
            },
            {"id": "missing", "type": "page", "url": "app://-/index.html"},
        ],
    )

    assert [target.id for target in targets] == ["devtools", "fallback", "exact"]
    assert select_codex_app_target(targets).id == "exact"
    assert select_codex_app_target(targets[:2]).id == "fallback"


def test_parse_cdp_targets_rejects_non_array() -> None:
    with pytest.raises(CodexAppCdpProtocolError, match="JSON array"):
        parse_cdp_targets({"not": "an array"})


def test_select_codex_app_target_rejects_missing_app_page() -> None:
    target = CdpTarget(
        id="browser",
        kind="page",
        url="https://example.com",
        websocket_debugger_url="ws://example",
    )

    with pytest.raises(CodexAppCdpConnectionError, match="app://"):
        select_codex_app_target([target])


def test_select_codex_app_target_uses_configurable_target_matchers() -> None:
    exact = CdpTarget(
        id="custom",
        kind="page",
        url="app://custom/index.html",
        websocket_debugger_url="ws://custom",
    )
    prefixed = CdpTarget(
        id="prefix",
        kind="page",
        url="app://custom/other.html",
        websocket_debugger_url="ws://prefix",
    )

    assert (
        select_codex_app_target(
            [prefixed, exact],
            target_url="app://custom/index.html",
            target_url_prefix="app://custom/",
        ).id
        == "custom"
    )
    assert (
        select_codex_app_target(
            [prefixed],
            target_url="app://custom/index.html",
            target_url_prefix="app://custom/",
        ).id
        == "prefix"
    )


def test_fetch_cdp_targets_reads_json_list_from_endpoint() -> None:
    server = JsonServer(
        status=200,
        body=[
            {
                "id": "target",
                "type": "page",
                "url": "app://-/index.html",
                "webSocketDebuggerUrl": "ws://target",
            },
        ],
    )

    try:
        targets = asyncio.run(fetch_cdp_targets(f"http://127.0.0.1:{server.port}/"))
    finally:
        server.close()

    assert targets == (
        CdpTarget(
            id="target",
            kind="page",
            url="app://-/index.html",
            websocket_debugger_url="ws://target",
        ),
    )
    assert server.paths == ["/json/list"]


def test_fetch_json_preserves_query_string_path() -> None:
    server = JsonServer(status=200, body=[])
    try:
        assert (
            cdp_targets._fetch_json(
                f"http://127.0.0.1:{server.port}/json/list?token=abc",
                10.0,
            )
            == []
        )
    finally:
        server.close()

    assert server.paths == ["/json/list?token=abc"]


def test_fetch_json_rejects_invalid_endpoint_and_http_errors() -> None:
    with pytest.raises(CodexAppCdpConnectionError, match="http or https"):
        cdp_targets._fetch_json("file:///json/list", 10.0)
    with pytest.raises(CodexAppCdpConnectionError, match="missing a host"):
        cdp_targets._fetch_json("http:///json/list", 10.0)

    server = JsonServer(status=500, body={"error": "bad"})
    try:
        with pytest.raises(CodexAppCdpConnectionError, match="HTTP 500"):
            cdp_targets._fetch_json(f"http://127.0.0.1:{server.port}/json/list", 10.0)
    finally:
        server.close()
