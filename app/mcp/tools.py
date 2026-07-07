"""MCP tool schema registration.

Two tools are exposed:

- `voice_over` converts text to speech, saves the result to a temp
  directory, and returns just the original text content plus the generated
  filename - the caller/deployment fetches the actual audio bytes via the
  REST download route.
- `visual_creator` turns a checklist of code/command entries (plus an
  optional base64-encoded project zip) into VS Code-style code screenshots
  and terminal-style command screenshots, saved as SVGs to a temp
  directory; the caller fetches each one via the REST download route.
"""

from __future__ import annotations

from mcp.types import Tool

from app.config import DEFAULT_PITCH, DEFAULT_RATE, DEFAULT_VOICE, DEFAULT_VOLUME
from app.core.vlogshot.themes import DEFAULT_THEME, THEMES
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
        Tool(
            name="visual_creator",
            description=(
                "Generate VS Code-style code screenshots and terminal-style "
                "command screenshots (as SVGs) for a coding vlog, from a "
                "checklist of entries. Each checklist entry is one of: "
                "(1) a zip-lookup code entry - {file, start_line, end_line, "
                "label} - resolved against 'zip_base64'; (2) an inline code "
                "entry - {path, start_line, code, label} - rendered directly, "
                "no zip needed; or (3) a command entry - "
                "{type: 'command', command, output, label} - rendered as a "
                "terminal window, no zip needed. 'zip_base64' is only "
                "required if at least one entry is a zip-lookup code entry. "
                "Returns per-entry status plus generated filenames; fetch "
                "each SVG's bytes via GET /api/v1/visual/{filename}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "checklist": {
                        "type": "array",
                        "description": (
                            "List of entries to render, in order. See tool "
                            "description for the three entry shapes."
                        ),
                        "items": {"type": "object"},
                    },
                    "zip_base64": {
                        "type": "string",
                        "default": None,
                        "description": (
                            "Base64-encoded project zip, required only if "
                            "'checklist' has a zip-lookup code entry."
                        ),
                    },
                    "theme": {
                        "type": "string",
                        "enum": sorted(THEMES.keys()),
                        "default": DEFAULT_THEME,
                        "description": "Color theme for code screenshots.",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["vscode", "minimal"],
                        "default": "vscode",
                        "description": (
                            "'vscode' for a full editor window (tabs, "
                            "breadcrumbs, minimap, status bar) or 'minimal' "
                            "for just a header bar."
                        ),
                    },
                    "font_size": {
                        "type": "integer",
                        "default": 22,
                        "description": "Font size in pixels.",
                    },
                    "width": {
                        "type": "integer",
                        "default": 1920,
                        "description": "Output image width in pixels (default: 1920, HD).",
                    },
                },
                "required": ["checklist"],
            },
        ),
    ]
