from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast
from urllib import error as url_error, request as url_request

from acodex.core.codex_app.cdp.errors import CodexCDPError
from acodex.core.codex_app.cdp.settings import CodexCDPSettings

TARGET_LIST_PATH = "/json/list"
PAGE_TARGET_TYPE = "page"
APP_URL_PREFIX = "app://-"


@dataclass(frozen=True, slots=True)
class CodexTargetDiscovery:
    """Discover the browser target for the Codex app renderer."""

    settings: CodexCDPSettings

    def find_target(self) -> dict[str, Any]:
        """Return the preferred Codex CDP target."""
        targets = self._load_targets()
        selector = CodexTargetSelector()
        selected_target = selector.select(targets)
        if selected_target is None:
            raise CodexCDPError("No page target found at {}".format(self.settings.base_url))
        return selected_target

    def _load_targets(self) -> list[Any]:
        try:
            with url_request.urlopen(  # noqa: S310 - CDP URL is explicit local config.
                "{}{}".format(self.settings.base_url, TARGET_LIST_PATH),
                timeout=self.settings.request_timeout,
            ) as response:
                targets_payload = json.loads(response.read().decode("utf-8"))
        except (OSError, url_error.URLError) as exc:
            raise CodexCDPError(
                "Could not reach Codex CDP at {}. Start Codex with --remote-debugging-port "
                "or set ACODEX_CODEX_APP_CDP_PORT.".format(self.settings.base_url),
            ) from exc

        if not isinstance(targets_payload, list) or not targets_payload:
            raise CodexCDPError("No CDP targets found at {}".format(self.settings.base_url))
        return cast("list[Any]", targets_payload)  # type: ignore[redundant-cast]


@dataclass(frozen=True, slots=True)
class CodexTargetSelector:
    """Select the best renderer page target from a CDP target list."""

    def select(self, targets: list[Any]) -> dict[str, Any] | None:
        """Return an app page target, then any page target as fallback."""
        app_target = self._first_app_page(targets)
        if app_target is not None:
            return app_target
        return self._first_page(targets)

    def _first_app_page(self, targets: list[Any]) -> dict[str, Any] | None:
        for target_payload in targets:
            if self._is_app_page_target(target_payload):
                return cast("dict[str, Any]", target_payload)
        return None

    def _first_page(self, targets: list[Any]) -> dict[str, Any] | None:
        for target_payload in targets:
            if not isinstance(target_payload, dict):
                continue
            typed_target = cast("dict[str, Any]", target_payload)
            if typed_target.get("type") == PAGE_TARGET_TYPE:
                return cast("dict[str, Any]", target_payload)
        return None

    def _is_app_page_target(self, target_payload: Any) -> bool:
        if not isinstance(target_payload, dict):
            return False
        typed_target = cast("dict[str, Any]", target_payload)
        target_url = typed_target.get("url", "")
        return (
            typed_target.get("type") == PAGE_TARGET_TYPE
            and isinstance(target_url, str)
            and target_url.startswith(APP_URL_PREFIX)
        )
