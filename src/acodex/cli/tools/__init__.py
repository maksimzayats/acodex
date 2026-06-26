from __future__ import annotations

from acodex.cli.server import ServerManager
from acodex.cli.tools.arguments import (
    JSONArgumentSource,
    OptionTokenParser,
    OptionTokenStream,
    SchemaArgumentNormalizer,
    ToolArgumentsParser,
    normalize_tool_arguments,
    parse_tool_arguments,
)
from acodex.cli.tools.client_provider import (
    ManagedMCPToolsClientProvider,
    MCPToolsClientFactory,
)
from acodex.cli.tools.command import ToolsCommand
from acodex.cli.tools.descriptors import (
    find_tool_descriptor,
    json_syntax,
    mcp_tool_result_shape,
    panel,
    tool_output_note,
    tool_output_shape,
    tool_result_text,
)
from acodex.cli.tools.models import ToolArgumentsError, ToolOutput
from acodex.cli.tools.presenter import ToolsPresenter
from acodex.core.mcp_tools import MCPToolsClient

__all__ = (
    "JSONArgumentSource",
    "MCPToolsClient",
    "MCPToolsClientFactory",
    "ManagedMCPToolsClientProvider",
    "OptionTokenParser",
    "OptionTokenStream",
    "SchemaArgumentNormalizer",
    "ServerManager",
    "ToolArgumentsError",
    "ToolArgumentsParser",
    "ToolOutput",
    "ToolsCommand",
    "ToolsPresenter",
    "find_tool_descriptor",
    "json_syntax",
    "mcp_tool_result_shape",
    "normalize_tool_arguments",
    "panel",
    "parse_tool_arguments",
    "tool_output_note",
    "tool_output_shape",
    "tool_result_text",
)
