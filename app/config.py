"""
Central configuration for the VoiceOver MCP Server.

All environment-variable reads live here. No other module should call
os.environ directly - import the constants from this file instead.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Server networking
# ---------------------------------------------------------------------------

PORT: int = int(os.environ.get("PORT", 8080))
HOST: str = os.environ.get("HOST", "0.0.0.0")

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
# Audio is generated to disk and immediately streamed back to the caller, so
# a single ephemeral temp directory is enough - no persistent volume needed.
# This matters for PaaS deployments (Render, Railway, Fly, etc.) where only
# /tmp is guaranteed writable and may be wiped between restarts.

TEMP_DIR_ENV = os.environ.get("TEMP_DIR", "")
TEMP_DIR: Path = (
    Path(TEMP_DIR_ENV).resolve()
    if TEMP_DIR_ENV
    else Path(tempfile.gettempdir()) / "voiceover_mcp"
)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# How long generated files are allowed to live before cleanup sweeps them.
AUDIO_TTL_SECONDS: int = int(os.environ.get("AUDIO_TTL_SECONDS", 3600))

# ---------------------------------------------------------------------------
# TTS defaults
# ---------------------------------------------------------------------------

DEFAULT_VOICE: str = os.environ.get("DEFAULT_VOICE", "en-IN-PrabhatNeural")
DEFAULT_RATE: str = os.environ.get("DEFAULT_RATE", "+0%")
DEFAULT_PITCH: str = os.environ.get("DEFAULT_PITCH", "+0Hz")
DEFAULT_VOLUME: str = os.environ.get("DEFAULT_VOLUME", "+0%")

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

MAX_LOG_ENTRIES: int = int(os.environ.get("MAX_LOG_ENTRIES", 1000))
APP_VERSION: str = "3.0.0"
APP_TITLE: str = "VoiceOver MCP Server"
