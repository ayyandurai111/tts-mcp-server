"""The MCP Server instance, shared by the tool-list and tool-call handlers."""

from __future__ import annotations

from mcp.server import Server

mcp_server = Server("voiceover-mcp-server")
