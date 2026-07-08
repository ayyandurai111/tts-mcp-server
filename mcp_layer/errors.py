"""Shared helper for building a standard {"success": false, "error": ...}
MCP tool response. Used by every tool's handler.py so all three tools
report failures the same way."""

from __future__ import annotations

import json

from mcp.types import TextContent

from common.logging import log_request


def error_response(name: str, arguments: dict, message: str) -> list[TextContent]:
    result = {"success": False, "error": message}
    log_request(name, arguments, result)
    return [TextContent(type="text", text=json.dumps(result, indent=2))]
