"""MCP registry - the only file that knows about every tool.

Aggregates each tool's schema.build_tool() and handler.handle() from
tools/{name}/, and wires them into the MCP server's list_tools/call_tool
hooks. Adding a new tool means adding one entry to _TOOL_HANDLERS below -
nothing else in mcp_layer/ needs to change.
"""

from __future__ import annotations

import json

from mcp.types import TextContent, Tool

from mcp_layer.server import mcp_server
from tools.video_renderer import handler as video_renderer_handler
from tools.video_renderer import schema as video_renderer_schema
from tools.visual_creator import handler as visual_creator_handler
from tools.visual_creator import schema as visual_creator_schema
from tools.voice_over import handler as voice_over_handler
from tools.voice_over import schema as voice_over_schema

_TOOL_HANDLERS = {
    "voice_over": voice_over_handler.handle,
    "visual_creator": visual_creator_handler.handle,
    "video_renderer": video_renderer_handler.handle,
}

_TOOL_SCHEMAS = [
    voice_over_schema.build_tool,
    visual_creator_schema.build_tool,
    video_renderer_schema.build_tool,
]


@mcp_server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [build() for build in _TOOL_SCHEMAS]


@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    arguments = arguments or {}
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return [
            TextContent(
                type="text",
                text=json.dumps({"success": False, "error": f"Unknown tool: {name}"}),
            )
        ]
    return await handler(arguments)
