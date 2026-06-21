from __future__ import annotations

from acodex.core.codex_app.assets.matcher import AssetMatchRecorder
from acodex.core.codex_app.assets.renderer_scan import RendererFallbackScanner, string_dict
from acodex.core.codex_app.assets.resource_tree import ResourceTreeScanner
from acodex.core.codex_app.cdp import CodexCDPClient


def missing_required_assets(matches: dict[str, str]) -> list[str]:
    return AssetMatchRecorder().missing_required(matches)


async def discover_assets_in_renderer(cdp: CodexCDPClient) -> dict[str, str]:
    return await RendererFallbackScanner().scan(cdp)


def string_dict_compat(raw_payload: object) -> dict[str, str]:
    return string_dict(raw_payload)


def collect_javascript_resources(frame_tree: dict[str, object]) -> list[tuple[str, str]]:
    resources = ResourceTreeScanner().collect(frame_tree)
    return [(resource.frame_id, resource.url) for resource in resources]
