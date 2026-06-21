from __future__ import annotations

from acodex.core.codex_app.assets.compat import (
    collect_javascript_resources as _collect_javascript_resources,
    discover_assets_in_renderer as _discover_assets_in_renderer,
    missing_required_assets as _missing_required_assets,
    string_dict_compat as _string_dict,
)
from acodex.core.codex_app.assets.discovery import RendererAssetDiscovery, discover_renderer_assets
from acodex.core.codex_app.assets.matcher import AssetMatchRecorder
from acodex.core.codex_app.assets.models import (
    CodexRendererAssetDiscoveryError,
    CodexRendererAssets,
)
from acodex.core.codex_app.assets.renderer_scan import RendererFallbackScanner, string_dict
from acodex.core.codex_app.assets.resource_tree import (
    JavaScriptResource,
    ResourceTreeAssetScanner,
    ResourceTreeScanner,
)

__all__ = (
    "AssetMatchRecorder",
    "CodexRendererAssetDiscoveryError",
    "CodexRendererAssets",
    "JavaScriptResource",
    "RendererAssetDiscovery",
    "RendererFallbackScanner",
    "ResourceTreeAssetScanner",
    "ResourceTreeScanner",
    "_collect_javascript_resources",
    "_discover_assets_in_renderer",
    "_missing_required_assets",
    "_string_dict",
    "discover_renderer_assets",
    "string_dict",
)
