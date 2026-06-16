from __future__ import annotations

from types import TracebackType

from typing_extensions import Self

from acodex.core.asyncio.cdp.errors import (
    CodexAppCdpConnectionError,
    CodexAppCdpDiscoveryError,
    CodexAppCdpError,
)
from acodex.core.asyncio.cdp.renderer import (
    build_tool_discovery_expression,
    build_tool_invocation_expression,
    parse_tool_discovery_result,
)
from acodex.core.asyncio.cdp.runtime import (
    CdpRuntime,
    CdpRuntimeConnector,
    WebsocketCdpRuntimeConnector,
)
from acodex.core.asyncio.cdp.settings import CodexAppCdpSettings
from acodex.core.asyncio.cdp.targets import (
    CdpTargetFetcher,
    CodexAppTargetSelector,
    HttpCdpTargetFetcher,
)
from acodex.core.asyncio.cdp.types import CdpTarget, CodexAppToolDiscovery, JsonObject, JsonValue
from acodex.core.asyncio.tools.base import AsyncRendererToolInvoker


class CodexAppCdpBackend(AsyncRendererToolInvoker):
    def __init__(
        self,
        *,
        settings: CodexAppCdpSettings | None = None,
        target_fetcher: CdpTargetFetcher | None = None,
        target_selector: CodexAppTargetSelector | None = None,
        runtime_connector: CdpRuntimeConnector | None = None,
    ) -> None:
        self.settings = settings or CodexAppCdpSettings()
        self.target: CdpTarget | None = None
        self.tool_discovery: CodexAppToolDiscovery | None = None
        self._target_fetcher = target_fetcher or HttpCdpTargetFetcher()
        self._target_selector = target_selector or CodexAppTargetSelector()
        self._runtime_connector = runtime_connector or WebsocketCdpRuntimeConnector()
        self._runtime: CdpRuntime | None = None

    @property
    def runtime(self) -> CdpRuntime | None:
        """Return the connected CDP runtime, when available."""
        return self._runtime

    async def __aenter__(self) -> Self:
        return await self.connect()

    async def __aexit__(  # noqa: PLR0917
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def connect(self) -> Self:
        """Connect to the Codex app renderer and discover available tools.

        Returns:
            This backend after the CDP runtime and renderer tool metadata are ready.

        Raises:
            CodexAppCdpError: If target selection, runtime evaluation, or discovery fails.

        """
        if self._runtime is not None:
            return self

        targets = await self._target_fetcher.fetch(
            self.settings.endpoint,
            http_timeout=self.settings.http_timeout,
        )
        self.target = self._target_selector.select(
            targets,
            target_url=self.settings.target_url,
            target_url_prefix=self.settings.target_url_prefix,
        )
        runtime = await self._runtime_connector.connect(
            self.target.websocket_debugger_url,
            runtime_timeout=self.settings.runtime_timeout,
        )
        self._runtime = runtime
        try:
            discovery_result = await runtime.evaluate(build_tool_discovery_expression())
            self.tool_discovery = parse_tool_discovery_result(discovery_result)
        except CodexAppCdpError:
            self._runtime = None
            self.tool_discovery = None
            await runtime.close()
            raise
        return self

    async def close(self) -> None:
        """Close the underlying CDP runtime when one is open."""
        runtime = self._runtime
        self._runtime = None
        if runtime is not None:
            await runtime.close()

    async def invoke_tool(
        self,
        tool_name: str,
        arguments: JsonObject,
        *,
        source_thread_id: str | None = None,
    ) -> JsonValue:
        """Invoke a discovered Codex app renderer tool.

        Returns:
            The renderer-native JSON result.

        Raises:
            CodexAppCdpDiscoveryError: If the requested tool was not discovered.
            CodexAppCdpConnectionError: If the runtime is unavailable after connecting.

        """
        if self._runtime is None:
            await self.connect()
        if self.tool_discovery is not None and tool_name not in self.tool_discovery.tool_names:
            raise CodexAppCdpDiscoveryError(f"Codex app tool was not discovered: {tool_name}")

        runtime = self._runtime
        if runtime is None:
            raise CodexAppCdpConnectionError("CDP runtime is not connected")

        return await runtime.evaluate(
            build_tool_invocation_expression(
                tool_name,
                arguments,
                source_thread_id=source_thread_id,
            ),
        )
