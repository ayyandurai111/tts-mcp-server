"""Regression tests for MCP transport wiring.

These cover two real production bugs found when connecting real MCP clients
(ChatGPT via Streamable HTTP, and a legacy SSE client):

1. `/mcp` must respond directly with no redirect (a 307 to "/mcp/" breaks
   clients that don't replay POST bodies through redirects).
2. `/mcp/messages` must actually exist and respond (was previously entirely
   unrouted, returning 404 for every tool call).

All three checks live in one test function deliberately: the underlying
StreamableHTTPSessionManager singleton can only have `.run()` entered once
per process, so the app lifespan (which enters it) must only be started
once across this test module.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.app import app

INIT_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    },
}
SSE_HEADERS = {"Accept": "application/json, text/event-stream"}


@pytest.mark.asyncio
async def test_mcp_transport_wiring():
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            # --- Streamable HTTP transport (/mcp) ---

            # Must succeed directly - no 307 redirect to /mcp/.
            init_resp = await client.post("/mcp", json=INIT_PAYLOAD, headers=SSE_HEADERS)
            assert init_resp.status_code == 200
            assert init_resp.json()["result"]["serverInfo"]["name"] == "voiceover-mcp-server"

            # Must expose both registered tools.
            tools_resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                headers=SSE_HEADERS,
            )
            assert tools_resp.status_code == 200
            tools = tools_resp.json()["result"]["tools"]
            assert {t["name"] for t in tools} == {"voice_over", "visual_creator", "video_renderer"}

            # --- Legacy SSE transport (/mcp/messages) ---

            # Previously a bare 404 (route didn't exist at all). 400 (missing
            # session_id) proves the route now exists and runs its logic; a
            # 307 would mean it's still hitting the Mount trailing-slash bug.
            messages_resp = await client.post("/mcp/messages", json={})
            assert messages_resp.status_code == 400
            assert "session_id" in messages_resp.text
