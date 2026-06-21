from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, cast

from acodex.core.codex_app.assets.matcher import AssetMatchRecorder
from acodex.core.codex_app.cdp import CodexCDPClient, CodexCDPError

APP_URL_PREFIX = "app://-"
SCRIPT_TYPE = "Script"


@dataclass(frozen=True, slots=True)
class JavaScriptResource:
    frame_id: str
    url: str


@dataclass(frozen=True, slots=True)
class ResourceTreeScanner:
    """Collect JavaScript resources from a CDP resource tree."""

    def collect(self, frame_tree: dict[str, Any]) -> list[JavaScriptResource]:
        """Return JavaScript resources in a frame tree."""
        resources: list[JavaScriptResource] = []
        pending_frames = [frame_tree]
        while pending_frames:
            frame_node = pending_frames.pop()
            resources.extend(self._node_resources(frame_node))
            pending_frames.extend(self._child_frames(frame_node))
        return resources

    def _node_resources(self, frame_node: dict[str, Any]) -> list[JavaScriptResource]:
        frame_payload = frame_node.get("frame", {})
        frame_id = None
        if isinstance(frame_payload, dict):
            frame_id = cast("dict[str, Any]", frame_payload).get("id")
        if not isinstance(frame_id, str):
            return []
        return [
            JavaScriptResource(frame_id=frame_id, url=resource_url)
            for resource_url in self._javascript_urls(frame_node)
        ]

    def _javascript_urls(self, frame_node: dict[str, Any]) -> list[str]:
        resource_urls: list[str] = []
        raw_resources = frame_node.get("resources", [])
        if not isinstance(raw_resources, list):
            return resource_urls
        resource_payloads = cast("list[Any]", raw_resources)  # type: ignore[redundant-cast]
        for resource_payload in resource_payloads:
            if not isinstance(resource_payload, dict):
                continue
            resource_url = self._resource_url(cast("dict[str, Any]", resource_payload))
            if resource_url is not None:
                resource_urls.append(resource_url)
        return resource_urls

    def _resource_url(self, resource_payload: dict[str, Any]) -> str | None:
        resource_url = resource_payload.get("url")
        if not isinstance(resource_url, str):
            return None
        if self._is_javascript_resource(resource_url, resource_payload):
            return resource_url
        return None

    def _is_javascript_resource(self, resource_url: str, resource_payload: dict[str, Any]) -> bool:
        return (
            resource_url.endswith(".js")
            or resource_payload.get("type") == SCRIPT_TYPE
            or "javascript" in str(resource_payload.get("mimeType", ""))
        )

    def _child_frames(self, frame_node: dict[str, Any]) -> list[dict[str, Any]]:
        raw_child_frames = frame_node.get("childFrames", [])
        if not isinstance(raw_child_frames, list):
            return []
        child_frames = cast("list[Any]", raw_child_frames)  # type: ignore[redundant-cast]
        return [
            cast("dict[str, Any]", child_frame)
            for child_frame in child_frames
            if isinstance(child_frame, dict)
        ]


@dataclass(frozen=True, kw_only=True, slots=True)
class ResourceTreeAssetScanner:
    """Scan readable resource-tree bundles for known asset signatures."""

    recorder: AssetMatchRecorder = field(default_factory=AssetMatchRecorder)
    resource_scanner: ResourceTreeScanner = field(default_factory=ResourceTreeScanner)

    async def scan(self, cdp: CodexCDPClient, frame_tree: dict[str, Any]) -> dict[str, str]:
        """Return asset role matches found from CDP resource contents."""
        resources = [
            resource
            for resource in self.resource_scanner.collect(frame_tree)
            if resource.url.startswith(APP_URL_PREFIX)
        ]
        resource_contents = await asyncio.gather(
            *(self._read_resource(cdp, resource) for resource in resources),
        )
        matches: dict[str, str] = {}
        for resource, bundle_content in zip(resources, resource_contents, strict=True):
            if bundle_content is not None:
                self.recorder.record(
                    matches,
                    bundle_content=bundle_content,
                    bundle_url=resource.url,
                )
        return matches

    async def _read_resource(
        self,
        cdp: CodexCDPClient,
        resource: JavaScriptResource,
    ) -> str | None:
        try:
            return await cdp.resource_content(resource.frame_id, resource.url)
        except CodexCDPError:
            return None
