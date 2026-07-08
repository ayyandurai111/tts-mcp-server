"""MCP tool schema for video_renderer."""

from __future__ import annotations

from mcp.types import Tool

from tools.video_renderer.core import DEFAULT_TRANSITION, TRANSITION_STYLES


def build_tool() -> Tool:
    return \
        Tool(
            name="video_renderer",
            description=(
                "Render a project's synced audio + visuals (built up via "
                "voice_over and visual_creator calls sharing a project_id) "
                "into a single MP4 video. Reads the project's manifest, "
                "requires every order to have both audio and a visual "
                "(orders missing either are skipped with a warning, not "
                "fatal), holds each order's screenshot(s) on screen for "
                "that order's narration duration, and concatenates every "
                "order in sequence. All orders must share one visual "
                "resolution. Output is saved to "
                "projects/{project_id}/final_output.mp4; fetch it via "
                "GET /api/v1/project/{project_id}/video."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": (
                            "Required. The project_id previously used in "
                            "matching voice_over/visual_creator calls."
                        ),
                    },
                    "transition": {
                        "type": "string",
                        "enum": list(TRANSITION_STYLES),
                        "default": DEFAULT_TRANSITION,
                        "description": (
                            "'cut' (default) joins order segments with a "
                            "hard cut - lossless, no re-encode of already-"
                            "rendered segments. 'crossfade' blends adjacent "
                            "segments with a short fade instead, at the "
                            "cost of a full re-encode and slightly "
                            "shortening total duration by the overlap."
                        ),
                    },
                    "crossfade_seconds": {
                        "type": "number",
                        "default": 0.5,
                        "description": (
                            "Only used when transition='crossfade'. Length "
                            "of the fade between adjacent order segments, "
                            "in seconds."
                        ),
                    },
                },
                "required": ["project_id"],
            },
        )
