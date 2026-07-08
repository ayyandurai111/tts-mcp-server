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

# visual_creator's generated SVG screenshots get their own flat subfolder of
# the same ephemeral temp dir, so they can be swept on their own TTL without
# touching audio files.
VISUALS_DIR: Path = TEMP_DIR / "visuals"
VISUALS_DIR.mkdir(parents=True, exist_ok=True)

# How long generated files are allowed to live before cleanup sweeps them.
AUDIO_TTL_SECONDS: int = int(os.environ.get("AUDIO_TTL_SECONDS", 3600))

# visual_creator (vlogshot) screenshots land in the same ephemeral temp dir
# as audio - same PaaS reasoning applies. Kept as a separate constant so the
# TTL can be tuned independently if needed.
VISUAL_TTL_SECONDS: int = int(os.environ.get("VISUAL_TTL_SECONDS", 3600))

# Projects: when voice_over/visual_creator are called with a project_id +
# order (i.e. as part of a vlog/video build, matching a skill's
# {"visuals": [...], "script": [...]} output), their files are additionally
# grouped under TEMP_DIR/projects/{project_id}/order_{NN}/ instead of only
# living in the flat audio/visual temp dirs. This is what makes later
# audio<->image sync possible: everything for one "beat" of the video sits
# in one folder, indexed by a manifest.json at the project root. See
# app/core/project_store.py.
PROJECTS_DIR: Path = TEMP_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_TTL_SECONDS: int = int(os.environ.get("PROJECT_TTL_SECONDS", 3600 * 6))

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

# ---------------------------------------------------------------------------
# video_renderer
# ---------------------------------------------------------------------------
# Path to the ffmpeg binary.
#
# This service deploys on Render's *native* Python runtime (render.yaml has
# no Dockerfile / apt-get hook - see buildCommand), so there is no OS
# package manager available at build time to `apt-get install ffmpeg`.
# `imageio-ffmpeg` (pinned in requirements.txt) solves this the same way
# resvg-py solves the "no system package" problem for SVG rasterization
# (see app/core/rasterize.py's docstring): it ships a static, self-
# contained ffmpeg binary as a pip package, so `pip install -r
# requirements.txt` alone is enough to provision it - no Dockerfile needed.
#
# FFMPEG_BINARY can still be overridden directly (e.g. to point at a system
# ffmpeg in a Docker-based deployment instead); if unset, resolve via
# imageio-ffmpeg first and only fall back to relying on $PATH if that
# package is unavailable for some reason.
def _resolve_ffmpeg_binary() -> str:
    override = os.environ.get("FFMPEG_BINARY")
    if override:
        return override
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - fall back to PATH lookup below
        return "ffmpeg"


FFMPEG_BINARY: str = _resolve_ffmpeg_binary()

# Default transition between order segments. "cut" is the only style
# guaranteed to work without re-encoding surprises; "crossfade" is a
# documented stretch-goal option (see app/core/render.py).
DEFAULT_TRANSITION: str = os.environ.get("DEFAULT_TRANSITION", "cut")

# How long a crossfade transition lasts, when requested.
CROSSFADE_SECONDS: float = float(os.environ.get("CROSSFADE_SECONDS", 0.5))

# ffmpeg render/encode timeout per subprocess call, so a stuck render can't
# hang a request forever on a PaaS free tier.
RENDER_TIMEOUT_SECONDS: int = int(os.environ.get("RENDER_TIMEOUT_SECONDS", 600))
