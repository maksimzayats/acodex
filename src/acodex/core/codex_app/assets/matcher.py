from __future__ import annotations

from dataclasses import dataclass

APP_SCOPE_KEY = "app_scope"
DYNAMIC_TOOLS_KEY = "dynamic_tools"
MANAGER_KEY = "manager"
VSCODE_API_KEY = "vscode_api"
REQUIRED_ASSET_KEYS = (APP_SCOPE_KEY, DYNAMIC_TOOLS_KEY, MANAGER_KEY)


@dataclass(frozen=True, slots=True)
class AssetMatchRecorder:
    """Detect Codex renderer bundle roles from JavaScript content."""

    def record(self, matches: dict[str, str], *, bundle_content: str, bundle_url: str) -> None:
        """Record any asset roles matched by one bundle."""
        if self._is_vscode_api_bundle(bundle_content):
            matches.setdefault(VSCODE_API_KEY, bundle_url)
        if self._is_dynamic_tools_bundle(bundle_content):
            matches.setdefault(DYNAMIC_TOOLS_KEY, bundle_url)
        if self._is_manager_bundle(bundle_content):
            matches.setdefault(MANAGER_KEY, bundle_url)
        if self._is_app_scope_bundle(bundle_content):
            matches.setdefault(APP_SCOPE_KEY, bundle_url)

    def missing_required(self, matches: dict[str, str]) -> list[str]:
        """Return the required asset keys missing from the current matches."""
        return [asset_key for asset_key in REQUIRED_ASSET_KEYS if asset_key not in matches]

    def _is_vscode_api_bundle(self, bundle_content: str) -> bool:
        return "vscode://codex/" in bundle_content and "sendMessageFromView" in bundle_content

    def _is_dynamic_tools_bundle(self, bundle_content: str) -> bool:
        return (
            "codex_app" in bundle_content
            and "list_threads" in bundle_content
            and "send_message_to_thread" in bundle_content
        )

    def _is_manager_bundle(self, bundle_content: str) -> bool:
        return (
            "read_thread_terminal" in bundle_content
            and "load_workspace_dependencies" in bundle_content
        )

    def _is_app_scope_bundle(self, bundle_content: str) -> bool:
        return (
            "queryClient" in bundle_content
            and "familyBindings" in bundle_content
            and ("__scopeBrand" in bundle_content or "Missing query client" in bundle_content)
        )
