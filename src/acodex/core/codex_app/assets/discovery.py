from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from acodex.core.codex_app.assets.matcher import (
    APP_SCOPE_KEY,
    DYNAMIC_TOOLS_KEY,
    MANAGER_KEY,
    VSCODE_API_KEY,
    AssetMatchRecorder,
)
from acodex.core.codex_app.assets.models import (
    CodexRendererAssetDiscoveryError,
    CodexRendererAssets,
)
from acodex.core.codex_app.assets.renderer_scan import RendererFallbackScanner
from acodex.core.codex_app.assets.resource_tree import ResourceTreeAssetScanner
from acodex.core.codex_app.cdp import CodexCDPClient


@dataclass(frozen=True, kw_only=True, slots=True)
class RendererAssetDiscovery:
    """Discover renderer bundles needed by the Codex app bridge."""

    recorder: AssetMatchRecorder = field(default_factory=AssetMatchRecorder)
    resource_scanner: ResourceTreeAssetScanner = field(default_factory=ResourceTreeAssetScanner)
    fallback_scanner: RendererFallbackScanner = field(default_factory=RendererFallbackScanner)

    async def discover(self, cdp: CodexCDPClient) -> CodexRendererAssets:
        """Find the renderer bundles needed to list and call Codex app tools."""
        frame_tree = self._frame_tree(await cdp.resource_tree())
        matches = await self.resource_scanner.scan(cdp, frame_tree)
        if self.recorder.missing_required(matches):
            matches.update(await self.fallback_scanner.scan(cdp))
        self._validate_matches(matches)
        return CodexRendererAssets(
            app_scope_url=matches[APP_SCOPE_KEY],
            dynamic_tools_url=matches[DYNAMIC_TOOLS_KEY],
            manager_url=matches[MANAGER_KEY],
            vscode_api_url=matches.get(VSCODE_API_KEY),
        )

    def _frame_tree(self, resource_tree: dict[str, object]) -> dict[str, object]:
        frame_tree = resource_tree.get("frameTree")
        if not isinstance(frame_tree, dict):
            raise CodexRendererAssetDiscoveryError(
                "CDP Page.getResourceTree returned no frame tree",
            )
        return cast("dict[str, Any]", frame_tree)

    def _validate_matches(self, matches: dict[str, str]) -> None:
        missing_assets = self.recorder.missing_required(matches)
        if missing_assets:
            raise CodexRendererAssetDiscoveryError(
                "Could not discover required Codex renderer assets: "
                "{}. Make sure the Codex app window is open and the current thread has loaded.".format(
                    ", ".join(missing_assets),
                ),
            )


async def discover_renderer_assets(cdp: CodexCDPClient) -> CodexRendererAssets:
    """Find the renderer bundles needed to list and call Codex app tools."""
    return await RendererAssetDiscovery().discover(cdp)
