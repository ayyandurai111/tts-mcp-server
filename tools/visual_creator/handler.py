"""MCP call_tool handler for visual_creator."""

from __future__ import annotations

import json

from mcp.types import TextContent

from common.config import VISUALS_DIR
from common.formatting import utc_now_iso
from common.logging import log_request
from mcp_layer.errors import error_response
from tools.visual_creator.core import VisualCreatorError, generate_visuals_core
from tools.visual_creator.vlogshot.themes import DEFAULT_THEME


async def handle(arguments: dict) -> list[TextContent]:
    name = "visual_creator"

    checklist = arguments.get("checklist")
    if not checklist:
        return error_response(name, arguments, "'checklist' cannot be empty.")

    try:
        outcome = generate_visuals_core(
            checklist=checklist,
            zip_base64=arguments.get("zip_base64"),
            persist_dir=VISUALS_DIR,
            theme=arguments.get("theme", DEFAULT_THEME),
            style=arguments.get("style", "vscode"),
            font_size=arguments.get("font_size", 22),
            image_width=arguments.get("width", 1920),
            image_height=arguments.get("height", 1080),
            output_format=arguments.get("output_format", "png"),
            project_id=arguments.get("project_id"),
        )

        result = {
            "success": True,
            "results": outcome["results"],
            "files": outcome["files"],
            "download_url_template": "/api/v1/visual/{filename}",
            "timestamp": utc_now_iso(),
        }
        if arguments.get("project_id"):
            result["project_id"] = arguments["project_id"]
        log_request(name, arguments, result)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except VisualCreatorError as exc:
        return error_response(name, arguments, str(exc))
    except Exception as exc:  # noqa: BLE001 - surface any unexpected failure safely
        return error_response(name, arguments, f"Unexpected error: {exc}")
