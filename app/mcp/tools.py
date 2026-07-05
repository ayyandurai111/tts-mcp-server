"""MCP tool schema registration.

Only one tool is exposed: `voice_over`. It converts text to speech, saves the
result to a temp directory, and returns just the original text content plus
the generated filename - the caller/deployment fetches the actual audio
bytes via the REST download route.
"""

from __future__ import annotations

from mcp.types import Tool

from app.config import DEFAULT_PITCH, DEFAULT_RATE, DEFAULT_VOICE, DEFAULT_VOLUME
from app.mcp.server import mcp_server


@mcp_server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="voice_over",
            description=(
                "Convert text to speech and save it as an MP3 in temporary "
                "storage. Returns the original text content and the "
                "generated filename; fetch the audio bytes via "
                "GET /api/v1/audio/{filename}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to convert to speech (required)",
                    },
                    "voice": {
                        "type": "string",
                        "default": DEFAULT_VOICE,
                        "description": "Voice ID, e.g. en-IN-PrabhatNeural, en-US-GuyNeural",
                    },
                    "rate": {
                        "type": "string",
                        "default": DEFAULT_RATE,
                        "description": "Speaking rate: +10% faster, -20% slower",
                    },
                    "pitch": {
                        "type": "string",
                        "default": DEFAULT_PITCH,
                        "description": "Voice pitch: +10Hz higher, -5Hz lower",
                    },
                    "volume": {
                        "type": "string",
                        "default": DEFAULT_VOLUME,
                        "description": "Volume: +10% louder, -20% quieter",
                    },
                    "output_filename": {
                        "type": "string",
                        "default": None,
                        "description": "Custom filename (optional)",
                    },
                },
                "required": ["text"],
            },
        ),
    ]
