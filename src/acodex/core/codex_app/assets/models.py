from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CodexRendererAssets:
    app_scope_url: str
    dynamic_tools_url: str
    manager_url: str
    vscode_api_url: str | None

    def as_payload(self) -> dict[str, str | None]:
        """Return the asset names expected by the renderer bridge script."""
        return {
            "appScopeUrl": self.app_scope_url,
            "dynamicToolsUrl": self.dynamic_tools_url,
            "managerUrl": self.manager_url,
            "vscodeApiUrl": self.vscode_api_url,
        }


class CodexRendererAssetDiscoveryError(RuntimeError):
    """Raised when required Codex renderer bundles cannot be discovered."""
