"""Filename generation and temp-directory path resolution."""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import AUDIO_TTL_SECONDS, TEMP_DIR

# Only allow safe characters in a user-supplied filename.
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize_filename(name: str) -> str:
    """Strip anything that isn't a safe filename character."""
    cleaned = _SAFE_NAME_RE.sub("_", name).strip("._")
    return cleaned or "audio"


def generate_filename(text: str, voice: str, custom_name: Optional[str] = None) -> str:
    """Generate a unique .mp3 filename, or sanitize a custom one."""
    if custom_name:
        safe = sanitize_filename(custom_name)
        return safe if safe.endswith(".mp3") else f"{safe}.mp3"

    unique = hashlib.sha256(
        f"{text}:{voice}:{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_voice = voice.replace("-", "_")
    return f"voiceover_{safe_voice}_{timestamp}_{unique}.mp3"


def resolve_temp_path(filename: str) -> Path:
    """Resolve a filename to a path inside the temp directory.

    Guards against path traversal by only ever using the basename.
    """
    safe_name = Path(filename).name
    return TEMP_DIR / safe_name


def cleanup_expired_files(ttl_seconds: int = AUDIO_TTL_SECONDS) -> int:
    """Delete temp audio files older than ttl_seconds. Returns count removed."""
    removed = 0
    now = time.time()
    for f in TEMP_DIR.glob("*.mp3"):
        try:
            if now - f.stat().st_mtime > ttl_seconds:
                f.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue
    return removed
