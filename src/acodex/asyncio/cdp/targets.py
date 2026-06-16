from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlparse

from acodex.asyncio.cdp.errors import CodexAppCdpConnectionError, CodexAppCdpProtocolError
from acodex.asyncio.cdp.json_utils import decode_json_value
from acodex.asyncio.cdp.settings import (
    DEFAULT_CDP_ENDPOINT,
    DEFAULT_CDP_HTTP_TIMEOUT,
    DEFAULT_CDP_TARGET_URL,
    DEFAULT_CDP_TARGET_URL_PREFIX,
)
from acodex.asyncio.cdp.types import CdpTarget, JsonValue

_HTTP_ERROR_STATUS = 400


async def fetch_cdp_targets(
    endpoint: str = DEFAULT_CDP_ENDPOINT,
    *,
    http_timeout: float = DEFAULT_CDP_HTTP_TIMEOUT,
) -> tuple[CdpTarget, ...]:
    """Fetch CDP targets from an endpoint's `/json/list` route.

    Returns:
        Parsed CDP targets that expose a websocket debugger URL.

    """
    return parse_cdp_targets(
        await asyncio.to_thread(_fetch_json, _json_list_url(endpoint), http_timeout),
    )


def parse_cdp_targets(value: JsonValue) -> tuple[CdpTarget, ...]:
    if not isinstance(value, list):
        raise CodexAppCdpProtocolError("CDP /json/list response must be a JSON array")

    targets: list[CdpTarget] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        target_id = _get_string(item, "id")
        kind = _get_string(item, "type")
        target_url = _get_string(item, "url")
        websocket_url = _get_string(item, "webSocketDebuggerUrl")
        if target_id is None or kind is None or target_url is None or websocket_url is None:
            continue

        targets.append(
            CdpTarget(
                id=target_id,
                kind=kind,
                url=target_url,
                websocket_debugger_url=websocket_url,
            ),
        )

    return tuple(targets)


def select_codex_app_target(
    targets: Sequence[CdpTarget],
    *,
    target_url: str = DEFAULT_CDP_TARGET_URL,
    target_url_prefix: str = DEFAULT_CDP_TARGET_URL_PREFIX,
) -> CdpTarget:
    exact_targets = [
        target for target in targets if target.kind == "page" and target.url.startswith(target_url)
    ]
    if exact_targets:
        return exact_targets[0]

    app_targets = [
        target
        for target in targets
        if target.kind == "page" and target.url.startswith(target_url_prefix)
    ]
    if app_targets:
        return app_targets[0]

    raise CodexAppCdpConnectionError("Could not find a Codex app:// page target in CDP")


def _json_list_url(endpoint: str) -> str:
    return f"{endpoint.rstrip('/')}/json/list"


def _fetch_json(url: str, timeout: float) -> JsonValue:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise CodexAppCdpConnectionError("CDP endpoint must use http or https")
    if parsed.hostname is None:
        raise CodexAppCdpConnectionError("CDP endpoint is missing a host")

    connection_class = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    connection = connection_class(parsed.hostname, parsed.port, timeout=timeout)
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        body = response.read()
    finally:
        connection.close()

    if response.status >= _HTTP_ERROR_STATUS:
        raise CodexAppCdpConnectionError(f"CDP endpoint returned HTTP {response.status}")
    return decode_json_value(body)


def _get_string(mapping: Mapping[str, JsonValue], key: str) -> str | None:
    value = mapping.get(key)
    return value if isinstance(value, str) else None
