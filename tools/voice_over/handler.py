"""MCP call_tool handler for voice_over."""

from __future__ import annotations

import json

from mcp.types import TextContent

from common.config import DEFAULT_PITCH, DEFAULT_RATE, DEFAULT_VOICE, DEFAULT_VOLUME
from common.files import generate_filename, resolve_temp_path
from common.formatting import utc_now_iso
from common.logging import log_request
from common.project_store import ProjectStoreError, save_audio_for_order
from mcp_layer.errors import error_response
from tools.voice_over.core import TTSGenerationError, generate_audio_core


async def handle(arguments: dict) -> list[TextContent]:
    name = "voice_over"

    text = arguments.get("text", "")
    if not text or not text.strip():
        return error_response(name, arguments, "Text cannot be empty.")

    voice = arguments.get("voice", DEFAULT_VOICE)
    project_id = arguments.get("project_id")
    order = arguments.get("order")

    if project_id and order is None:
        return error_response(
            name, arguments,
            "'order' is required when 'project_id' is given, so this audio "
            "can be grouped with its matching visual for sync.",
        )

    try:
        filename = generate_filename(text, voice, arguments.get("output_filename"))
        output_path = resolve_temp_path(filename)

        audio_info = await generate_audio_core(
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
            "duration_seconds": audio_info.get("duration_seconds"),
            "timestamp": utc_now_iso(),
        }

        if project_id:
            try:
                save_audio_for_order(
                    project_id=project_id,
                    order=order,
                    src_audio_path=output_path,
                    label=arguments.get("label"),
                    script_text=text,
                    duration_seconds=audio_info.get("duration_seconds"),
                )
                result["project_id"] = project_id
                result["order"] = order
                result["project_file"] = f"projects/{project_id}/order_{order:02d}/audio.mp3"
            except ProjectStoreError as exc:
                result["project_warning"] = f"Audio generated, but project sync save failed: {exc}"

        log_request(name, arguments, result)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except TTSGenerationError as exc:
        return error_response(name, arguments, str(exc))
    except Exception as exc:  # noqa: BLE001 - surface any unexpected failure safely
        return error_response(name, arguments, f"Unexpected error: {exc}")
