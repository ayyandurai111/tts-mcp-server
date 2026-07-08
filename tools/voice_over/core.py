"""Core text-to-speech generation logic (transport-agnostic)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import edge_tts

from common.config import DEFAULT_PITCH, DEFAULT_RATE, DEFAULT_VOICE, DEFAULT_VOLUME
from common.formatting import human_file_size


class TTSGenerationError(Exception):
    """Raised when edge-tts fails to synthesize or save audio."""


def _read_mp3_duration_seconds(path: Path) -> Optional[float]:
    """Best-effort MP3 duration in seconds, or None if it can't be read.

    Used to populate the project sync manifest (app/core/project_store.py)
    so a later sync/render step knows how long each screenshot should stay
    on screen without needing to probe the file itself. Failure here is
    non-fatal - TTS generation has already succeeded by this point, so a
    missing duration just means the sync tool will need to probe the file
    itself later.
    """
    try:
        from mutagen.mp3 import MP3

        return round(MP3(str(path)).info.length, 3)
    except Exception:  # noqa: BLE001 - duration is best-effort, never fail generation over it
        return None


async def generate_audio_core(
    text: str,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
    volume: str = DEFAULT_VOLUME,
) -> dict:
    """Synthesize `text` to an mp3 at `output_path` using edge-tts.

    Returns metadata about the resulting file, including a best-effort
    `duration_seconds` (None if it couldn't be determined). Raises
    TTSGenerationError on failure (network issues, invalid voice, empty
    output, etc.).
    """
    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume=volume,
        )
        await communicate.save(str(output_path))
    except Exception as exc:  # noqa: BLE001 - normalize all edge_tts failures
        raise TTSGenerationError(str(exc)) from exc

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise TTSGenerationError("Audio file was not generated or is empty.")

    file_size = output_path.stat().st_size
    return {
        "file_path": str(output_path),
        "file_name": output_path.name,
        "file_size_bytes": file_size,
        "file_size_human": human_file_size(file_size),
        "duration_seconds": _read_mp3_duration_seconds(output_path),
    }


async def list_available_voices(language: str | None = None, gender: str | None = None) -> list[dict]:
    """Return available edge-tts voices, optionally filtered."""
    voices = await edge_tts.list_voices()

    if language:
        voices = [v for v in voices if v["Locale"].lower().startswith(language.lower())]
    if gender:
        voices = [v for v in voices if v.get("Gender", "").lower() == gender.lower()]

    voices.sort(key=lambda v: (v["Locale"], v["ShortName"]))

    return [
        {
            "name": v["ShortName"],
            "locale": v["Locale"],
            "gender": v.get("Gender", "Unknown"),
            "friendly_name": v.get("FriendlyName", v["ShortName"]),
        }
        for v in voices[:200]
    ]
