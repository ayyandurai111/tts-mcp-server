"""MCP tool schema for voice_over."""

from __future__ import annotations

from mcp.types import Tool

from common.config import DEFAULT_PITCH, DEFAULT_RATE, DEFAULT_VOICE, DEFAULT_VOLUME


def build_tool() -> Tool:
    return \
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
                    "project_id": {
                        "type": "string",
                        "default": None,
                        "description": (
                            "Optional. Groups this audio with a matching "
                            "visual_creator screenshot for later audio<->"
                            "image sync (e.g. building a dev vlog from a "
                            "skill's {\"visuals\": [...], \"script\": [...]} "
                            "output). When set, 'order' is required. The "
                            "audio is additionally copied to "
                            "projects/{project_id}/order_{order:02d}/audio.mp3 "
                            "and recorded (with its duration) in that "
                            "project's manifest.json, alongside whatever "
                            "visual_creator saves for the same project_id "
                            "and order."
                        ),
                    },
                    "order": {
                        "type": "integer",
                        "default": None,
                        "description": (
                            "Required when 'project_id' is set. The beat/"
                            "step number this narration belongs to - the "
                            "same 'order' the matching checklist entry has "
                            "in the visual_creator call, so the two are "
                            "filed together for sync."
                        ),
                    },
                    "label": {
                        "type": "string",
                        "default": None,
                        "description": (
                            "Optional, only used with 'project_id'. A short "
                            "label for this beat (e.g. the checklist "
                            "entry's own 'label'), stored in the project "
                            "manifest for readability."
                        ),
                    },
                },
                "required": ["text"],
            },
        )
