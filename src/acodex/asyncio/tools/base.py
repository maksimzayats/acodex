from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar, Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from acodex.asyncio.cdp.errors import CodexAppCdpProtocolError
from acodex.asyncio.cdp.json_utils import ensure_json_value
from acodex.asyncio.cdp.types import JsonObject, JsonValue

ToolOutputT = TypeVar("ToolOutputT", bound=BaseModel)


class AsyncRendererToolInvoker(Protocol):
    async def __call__(
        self,
        tool_name: str,
        arguments: JsonObject,
        *,
        source_thread_id: str | None = None,
    ) -> JsonValue:
        """Invoke a renderer tool with an already serialized JSON object.

        Returns:
            The renderer-native JSON result.

        """
        ...


class RendererToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RendererToolContentItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["inputText"]
    text: str


class RendererToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    content_items: list[RendererToolContentItem] = Field(validation_alias="contentItems")
    success: bool


class BaseAsyncTool(Generic[ToolOutputT]):
    NAME: ClassVar[str]
    INPUT_TYPE: ClassVar[object]
    OUTPUT_TYPE: ClassVar[type[ToolOutputT]]

    def __init__(self, invoker: AsyncRendererToolInvoker) -> None:
        self._invoker = invoker

    async def _invoke(
        self,
        arguments: object,
        *,
        source_thread_id: str | None = None,
    ) -> ToolOutputT:
        renderer_payload = dump_tool_input(self.INPUT_TYPE, arguments)
        result = await self._invoker(
            self.NAME,
            renderer_payload,
            source_thread_id=source_thread_id,
        )
        return parse_tool_output(self.OUTPUT_TYPE, result)


def dump_tool_input(input_type: Any, payload: object) -> JsonObject:
    """Dump a TypedDict payload with Pydantic aliases for renderer invocation.

    Pydantic's TypeAdapter accepts typing objects, including TypedDict classes,
    which are intentionally represented as Any at this narrow integration point.

    Returns:
        The renderer-native JSON object payload.

    Raises:
        CodexAppCdpProtocolError: If the payload has unknown keys or does not dump to an object.

    """
    _reject_unknown_tool_input_keys(input_type, payload)
    adapter = TypeAdapter(input_type)
    validated = adapter.validate_python(payload)
    dumped = adapter.dump_python(validated, by_alias=True, exclude_none=True)
    json_value = ensure_json_value(dumped)
    if not isinstance(json_value, dict):
        raise CodexAppCdpProtocolError("Renderer tool input must dump to a JSON object")
    return json_value


def parse_tool_output(output_type: type[ToolOutputT], result: JsonValue) -> ToolOutputT:
    json_value = unwrap_renderer_tool_result(result)
    if not isinstance(json_value, dict):
        raise CodexAppCdpProtocolError("Renderer tool output must be a JSON object")
    return output_type.model_validate(json_value)


def unwrap_renderer_tool_result(result: JsonValue) -> JsonValue:
    if not isinstance(result, dict) or "contentItems" not in result or "success" not in result:
        return ensure_json_value(result)

    envelope = RendererToolEnvelope.model_validate(result)
    if len(envelope.content_items) == 0:
        raise CodexAppCdpProtocolError("Renderer tool output is missing contentItems")

    content_item = envelope.content_items[0]
    if not envelope.success:
        raise CodexAppCdpProtocolError(content_item.text)

    try:
        decoded: object = json.loads(content_item.text)
    except json.JSONDecodeError as error:
        raise CodexAppCdpProtocolError("Renderer tool output text must be JSON") from error
    return ensure_json_value(decoded)


def _reject_unknown_tool_input_keys(input_type: object, payload: object) -> None:
    if not isinstance(payload, Mapping):
        return
    annotations = getattr(input_type, "__annotations__", {})
    if not isinstance(annotations, Mapping):
        return
    unknown_keys = sorted(set(payload) - set(annotations))
    if unknown_keys:
        joined_keys = ", ".join(unknown_keys)
        raise CodexAppCdpProtocolError(f"Unknown renderer tool input keys: {joined_keys}")
