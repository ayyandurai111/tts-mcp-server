"""Streamable HTTP transport (2025-03+ spec) - a single endpoint supporting
GET/POST/DELETE. This is what modern MCP clients (including ChatGPT's
connector UI) expect; the legacy two-endpoint SSE transport (sse_asgi.py) is
kept alongside it for older clients.

`stateless=True` is used deliberately: Render's free plan can spin the
instance down and lose all in-memory state at any time, so per-request
statelessness avoids "session not found" errors after a cold start.
"""

from __future__ import annotations

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from mcp_layer.server import mcp_server

# Ensure tool/handler registration has happened (safe if already imported).
from mcp_layer import registry as _registry  # noqa: F401 - side-effect import registers list_tools/call_tool

http_session_manager = StreamableHTTPSessionManager(
    app=mcp_server,
    json_response=True,
    stateless=True,
)


class StreamableHTTPASGIApp:
    """Thin raw-ASGI wrapper so Starlette's Mount treats this as an ASGI app
    (not a request/response endpoint needing a Response return value)."""

    def __init__(self, manager: StreamableHTTPSessionManager) -> None:
        self.manager = manager

    async def __call__(self, scope, receive, send) -> None:
        await self.manager.handle_request(scope, receive, send)


streamable_http_app = StreamableHTTPASGIApp(http_session_manager)

