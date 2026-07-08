"""MCP call_tool handler for video_renderer."""

from __future__ import annotations

import json

from mcp.types import TextContent

from common.config import BASE_URL
from common.formatting import utc_now_iso
from common.logging import log_request
from common.project_store import (
    ProjectStoreError,
    get_manifest,
    project_dir,
    save_final_video,
)
from mcp_layer.errors import error_response
from tools.video_renderer.core import DEFAULT_TRANSITION, VideoRenderError, render_project_video


async def handle(arguments: dict) -> list[TextContent]:
    name = "video_renderer"

    project_id = arguments.get("project_id")
    if not project_id or not str(project_id).strip():
        return error_response(name, arguments, "'project_id' cannot be empty.")

    transition = arguments.get("transition", DEFAULT_TRANSITION)
    crossfade_seconds = arguments.get("crossfade_seconds", 0.5)

    try:
        if not project_dir(project_id).exists():
            return error_response(name, arguments, f"Unknown project_id '{project_id}'.")

        manifest = get_manifest(project_id)
        out_path = project_dir(project_id) / "_rendering_output.mp4"

        outcome = render_project_video(
            manifest=manifest,
            out_path=out_path,
            transition=transition,
            crossfade_seconds=crossfade_seconds,
        )

        final_path = save_final_video(project_id, out_path)
        out_path.unlink(missing_ok=True)

        relative_url = f"/api/v1/project/{project_id}/video"
        download_url = f"{BASE_URL.rstrip('/')}{relative_url}" if BASE_URL else relative_url

        result = {
            "success": True,
            "project_id": project_id,
            "filename": final_path.name,
            "total_duration_seconds": outcome["total_duration_seconds"],
            "transition": outcome["transition"],
            "orders": outcome["orders"],
            "warnings": outcome["warnings"],
            "download_url": download_url,
            "timestamp": utc_now_iso(),
        }
        log_request(name, arguments, result)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except (VideoRenderError, ProjectStoreError) as exc:
        return error_response(name, arguments, str(exc))
    except Exception as exc:  # noqa: BLE001 - surface any unexpected failure safely
        return error_response(name, arguments, f"Unexpected error: {exc}")
