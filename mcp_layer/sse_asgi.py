"""Raw ASGI apps for the legacy MCP-over-SSE transport (2024-11-05 spec).

Mounted directly with Starlette's `Mount`/`Route` (bypassing FastAPI's usual
request/response wrapping) because this transport manages its own ASGI
response lifecycle. This mirrors the pattern used internally by the official
MCP Python SDK (see mcp.server.fastmcp.server and mcp.server.sse docstring).
"""

from __future__ import annotations

from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from mcp.server.sse import SseServerTransport

from mcp_layer.server import mcp_server

# Importing tools/handlers registers the @mcp_server decorators.
from mcp_layer import registry as _registry  # noqa: F401 - side-effect import registers list_tools/call_tool

# Full path the client is told to POST JSON-RPC messages to.
sse_transport = SseServerTransport("/mcp/messages")


async def handle_sse(scope: Scope, receive: Receive, send: Send) -> Response:
    """GET /mcp/sse - open the SSE stream and run the MCP session on it.

    IMPORTANT: must return a Response, or Starlette raises
    'TypeError: NoneType object is not callable' once the SSE session ends
    (documented behavior of mcp.server.sse.SseServerTransport).
    """
    async with sse_transport.connect_sse(scope, receive, send) as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )
    return Response()


async def sse_endpoint(request):  # Starlette Route adapter (needs a Request-taking fn)
    return await handle_sse(request.scope, request.receive, request._send)


class _PostMessageASGIApp:
    """Wraps sse_transport.handle_post_message (a bound method) in a plain
    class instance, so Starlette's Route treats it as raw ASGI (exact path
    match, no wrapping) instead of a function/method needing request_response
    conversion - and critically, instead of Mount, which would 307-redirect
    POST /mcp/messages to POST /mcp/messages/ and drop the request body on
    clients that don't replay POST through redirects.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await sse_transport.handle_post_message(scope, receive, send)


handle_post_message = _PostMessageASGIApp()
