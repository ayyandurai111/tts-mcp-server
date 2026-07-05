"""FastAPI application factory: middleware, lifespan, and router wiring."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import Route

from app.config import APP_TITLE, APP_VERSION, HOST, PORT, TEMP_DIR
from app.core.files import cleanup_expired_files
from app.mcp.sse_asgi import handle_post_message, sse_endpoint
from app.mcp.streamable_http_asgi import http_session_manager, streamable_http_app
from app.routes import audio, logs, root, tts, voices


@asynccontextmanager
async def lifespan(app: FastAPI):
    removed = cleanup_expired_files()
    print(f"VoiceOver MCP Server starting on http://{HOST}:{PORT}", file=sys.stderr)
    print(f"Temp audio directory: {TEMP_DIR}", file=sys.stderr)
    if removed:
        print(f"Cleaned up {removed} expired audio file(s) on startup", file=sys.stderr)

    # The Streamable HTTP session manager needs its task group running for
    # the lifetime of the app - without this, handle_request() raises
    # "Task group is not initialized."
    async with http_session_manager.run():
        yield

    print("Shutting down VoiceOver MCP Server", file=sys.stderr)


def create_app() -> FastAPI:
    app = FastAPI(
        title=APP_TITLE,
        description="Text-to-speech via MCP (Streamable HTTP + legacy SSE) and REST API.",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(root.router)
    app.include_router(tts.router)
    app.include_router(voices.router)
    app.include_router(audio.router)
    app.include_router(logs.router)

    # --- MCP transports: mounted as raw ASGI (bypasses FastAPI's response
    # wrapping, which these protocol-level streams manage themselves) ---

    # Modern Streamable HTTP transport (single endpoint) - required by
    # ChatGPT's connector UI and other current-generation MCP clients.
    # `streamable_http_app` is a class instance (not a plain function), so
    # Starlette's Route treats it as a raw ASGI app: exact path match on
    # "/mcp" with no trailing-slash redirect and no response-object wrapping.
    app.router.routes.append(
        Route("/mcp", endpoint=streamable_http_app, methods=["GET", "POST", "DELETE"])
    )

    # Legacy SSE transport (two endpoints) - kept for older MCP clients
    # (e.g. some Claude Desktop versions / mcp-remote bridge). Both use
    # exact-path Route matching (not Mount) to avoid trailing-slash redirects.
    app.router.routes.append(Route("/mcp/sse", endpoint=sse_endpoint, methods=["GET"]))
    app.router.routes.append(
        Route("/mcp/messages", endpoint=handle_post_message, methods=["POST"])
    )

    return app


app = create_app()

