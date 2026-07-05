"""MCP call_tool dispatch logic."""

from __future__ import annotations

import json

from mcp.types import TextContent

from app.config import DEFAULT_PITCH, DEFAULT_RATE, DEFAULT_VOICE, DEFAULT_VOLUME
from app.core.files import generate_filename, resolve_temp_path
from app.core.logging import log_request
from app.core.tts import TTSGenerationError, generate_audio_core
from app.mcp.server import mcp_server
from app.utils.formatting import utc_now_iso


def _error(name: str, arguments: dict, message: str) -> list[TextContent]:
    result = {"success": False, "error": message}
    log_request(name, arguments, result)
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    arguments = arguments or {}

    if name != "voice_over":
        return [
            TextContent(
                type="text",
                text=json.dumps({"success": False, "error": f"Unknown tool: {name}"}),
            )
        ]

    text = arguments.get("text", "")
    if not text or not text.strip():
        return _error(name, arguments, "Text cannot be empty.")

    voice = arguments.get("voice", DEFAULT_VOICE)

    try:
        filename = generate_filename(text, voice, arguments.get("output_filename"))
        output_path = resolve_temp_path(filename)

        await generate_audio_core(
            text=text,
            output_path=output_path,
            voice=voice,
            rate=arguments.get("rate", DEFAULT_RATE),
            pitch=arguments.get("pitch", DEFAULT_PITCH),
            volume=arguments.get("volume", DEFAULT_VOLUME),
        )

        result = {
            "success": True,
            "content": text,
            "filename": output_path.name,
            "timestamp": utc_now_iso(),
        }
        log_request(name, arguments, result)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except TTSGenerationError as exc:
        return _error(name, arguments, str(exc))
    except Exception as exc:  # noqa: BLE001 - surface any unexpected failure safely
        return _error(name, arguments, f"Unexpected error: {exc}")
