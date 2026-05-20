from __future__ import annotations

import logging
import os
import re
from typing import Any
from typing import Sequence

from mcp import StdioServerParameters

from .config import McpServerConfig
from .config import load_mcp_servers

logger = logging.getLogger(__name__)

try:
    from google.adk.tools.mcp_tool import McpToolset as _BaseMcpToolset
except ImportError:  # pragma: no cover
    _BaseMcpToolset = None


class CappedMcpToolset(_BaseMcpToolset if _BaseMcpToolset else object):
    def __init__(
        self,
        *,
        max_tools: int,
        include_name_patterns: list[str],
        required_tool_names: list[str],
        **kwargs,
    ):
        if _BaseMcpToolset is None:
            raise ImportError("MCP tools not available in ADK installation")
        super().__init__(**kwargs)
        self.max_tools = max_tools
        self.include_name_patterns = include_name_patterns
        self.required_tool_names = set(required_tool_names)

    async def get_tools(self, readonly_context=None):
        tools = await super().get_tools(readonly_context)

        if self.include_name_patterns:
            compiled = [re.compile(p) for p in self.include_name_patterns if p]
            if compiled:
                tools = [
                    tool
                    for tool in tools
                    if any(rx.search(tool.name) for rx in compiled)
                ]

        if self.required_tool_names:
            required = [t for t in tools if t.name in self.required_tool_names]
            rest = [t for t in tools if t.name not in self.required_tool_names]
            tools = required + rest

        if self.max_tools > 0:
            return tools[: self.max_tools]
        return tools


def _build_stdio_toolset(
    server: McpServerConfig,
    tool_filter: Sequence[str] | None = None,
) -> Any | None:
    try:
        from google.adk.tools.mcp_tool import StdioConnectionParams
    except ImportError as exc:
        logger.warning("MCP tools not available in ADK: %s", exc)
        return None

    if not server.command:
        logger.warning("MCP server '%s' skipped: missing command", server.name)
        return None
    if any(not str(arg).strip() for arg in server.args):
        logger.warning("MCP server '%s' skipped: invalid args", server.name)
        return None

    merged_env = os.environ.copy()
    merged_env.update(server.env)

    params = StdioConnectionParams(
        server_params=StdioServerParameters(
            command=server.command,
            args=server.args,
            env=merged_env,
        ),
        timeout=server.timeout_seconds,
    )

    return CappedMcpToolset(
        connection_params=params,
        max_tools=server.max_tools,
        include_name_patterns=server.include_name_patterns,
        required_tool_names=server.required_tool_names,
        tool_name_prefix=server.tool_name_prefix,
        tool_filter=list(tool_filter) if tool_filter else None,
    )


def _build_streamable_http_toolset(
    server: McpServerConfig,
    tool_filter: Sequence[str] | None = None,
) -> Any | None:
    try:
        from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
    except ImportError as exc:
        logger.warning("MCP tools not available in ADK: %s", exc)
        return None

    if not server.url:
        logger.warning("MCP server '%s' skipped: missing url", server.name)
        return None

    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    headers.update(server.headers)

    params = StreamableHTTPConnectionParams(
        url=server.url,
        headers=headers,
        timeout=server.timeout_seconds,
    )

    return CappedMcpToolset(
        connection_params=params,
        max_tools=server.max_tools,
        include_name_patterns=server.include_name_patterns,
        required_tool_names=server.required_tool_names,
        tool_name_prefix=server.tool_name_prefix,
        tool_filter=list(tool_filter) if tool_filter else None,
    )


def build_mcp_toolsets(tool_filter: Sequence[str] | None = None) -> list[Any]:
    toolsets: list[Any] = []
    for server in load_mcp_servers():
        if not server.enabled:
            continue

        transport = server.transport.lower().strip()
        if transport == "stdio":
            toolset = _build_stdio_toolset(server, tool_filter=tool_filter)
        elif transport in {"streamable_http", "http", "https"}:
            toolset = _build_streamable_http_toolset(server, tool_filter=tool_filter)
        else:
            logger.warning(
                "MCP server '%s' skipped: unsupported transport '%s'",
                server.name,
                server.transport,
            )
            continue

        if toolset is not None:
            toolsets.append(toolset)

    return toolsets
