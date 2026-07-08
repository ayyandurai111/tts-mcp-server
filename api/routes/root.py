"""Root '/' and '/health' endpoints."""

from __future__ import annotations

import os

from fastapi import APIRouter

from common.config import APP_VERSION, DEFAULT_VOICE, TEMP_DIR

router = APIRouter(tags=["meta"])


@router.get("/")
async def root():
    return {
        "service": "VoiceOver MCP Server",
        "version": APP_VERSION,
        "endpoints": {
            "mcp_streamable_http": "/mcp",
            "mcp_sse_legacy": "/mcp/sse",
            "rest_tts": "POST /api/v1/tts",
            "rest_voices": "GET /api/v1/voices",
            "rest_audio": "GET /api/v1/audio/{filename}",
            "rest_visual": "GET /api/v1/visual/{filename}",
            "health": "GET /health",
            "docs": "/docs",
        },
    }


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "temp_dir": str(TEMP_DIR),
        "temp_dir_exists": TEMP_DIR.exists(),
        "temp_dir_writable": os.access(TEMP_DIR, os.W_OK),
        "default_voice": DEFAULT_VOICE,
    }
