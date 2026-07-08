"""MCP tool schema for visual_creator."""

from __future__ import annotations

from mcp.types import Tool

from tools.visual_creator.core import OUTPUT_FORMATS
from tools.visual_creator.vlogshot.themes import DEFAULT_THEME, THEMES


def build_tool() -> Tool:
    return \
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
                        "description": "Fixed output image width in pixels (default: 1920, HD).",
                    },
                    "height": {
                        "type": "integer",
                        "default": 1080,
                        "description": (
                            "Fixed output image height in pixels (default: "
                            "1080). Every screenshot is rendered at exactly "
                            "this width x height regardless of how many "
                            "lines of code it contains, so a whole batch of "
                            "screenshots is video-ready with no size "
                            "mismatches between clips (important when "
                            "syncing screenshots to narration/TTS audio in "
                            "a video timeline). Code always starts at the "
                            "top of the canvas, like a real editor; short "
                            "snippets just leave empty space at the bottom. "
                            "Snippets too long to fit at the chosen font "
                            "size are automatically split into multiple "
                            "same-sized screenshots (e.g. '01_foo.svg', "
                            "'01_foo_p2.svg') rather than being shrunk or "
                            "cut off."
                        ),
                    },
                    "output_format": {
                        "type": "string",
                        "enum": list(OUTPUT_FORMATS),
                        "default": "png",
                        "description": (
                            "'png' (default) for a high-resolution (>=4K on "
                            "the long edge) rasterized PNG, rendered "
                            "directly from vector source at generation "
                            "time; 'svg' for the raw vector output instead; "
                            "'both' to keep both files."
                        ),
                    },
                    "project_id": {
                        "type": "string",
                        "default": None,
                        "description": (
                            "Optional. Groups every checklist entry's "
                            "screenshot(s) with a matching voice_over "
                            "narration for later audio<->image sync (e.g. "
                            "building a dev vlog from a skill's "
                            "{\"visuals\": [...], \"script\": [...]} "
                            "output, matched by 'order'). When set, each "
                            "entry's rendered file(s) are additionally "
                            "copied to "
                            "projects/{project_id}/order_{entry.order:02d}/"
                            "visual.<ext> (or visual_p1.<ext>, "
                            "visual_p2.<ext>, ... if paginated), recorded "
                            "in that project's manifest.json alongside "
                            "whatever voice_over saves for the same "
                            "project_id and order. The checklist's own "
                            "'order' field on each entry is what's used - "
                            "make sure it matches the 'order' used in the "
                            "corresponding voice_over calls."
                        ),
                    },
                },
                "required": ["checklist"],
            },
        )
