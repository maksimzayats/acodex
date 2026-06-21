from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from acodex.core.codex_app.assets.fallback_script import RENDERER_ASSET_DISCOVERY_EXPRESSION
from acodex.core.codex_app.cdp import CodexCDPClient


@dataclass(frozen=True, slots=True)
class RendererFallbackScanner:
    """Ask the renderer to scan its loaded JavaScript bundles."""

    async def scan(self, cdp: CodexCDPClient) -> dict[str, str]:
        """Return asset matches found by renderer-side scanning."""
        scan_result = await cdp.evaluate(RENDERER_ASSET_DISCOVERY_EXPRESSION, await_promise=True)
        if isinstance(scan_result, str):
            return string_dict(json.loads(scan_result))
        return string_dict(scan_result)


def string_dict(raw_payload: Any) -> dict[str, str]:
    if not isinstance(raw_payload, dict):
        return {}
    payload = cast("dict[Any, Any]", raw_payload)  # type: ignore[redundant-cast]
    return {
        str(payload_key): payload_value
        for payload_key, payload_value in payload.items()
        if isinstance(payload_value, str)
    }
