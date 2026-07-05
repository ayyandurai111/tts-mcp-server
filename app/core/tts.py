"""Core text-to-speech generation logic (transport-agnostic)."""

from __future__ import annotations

from pathlib import Path

import edge_tts

from app.config import DEFAULT_PITCH, DEFAULT_RATE, DEFAULT_VOICE, DEFAULT_VOLUME
from app.utils.formatting import human_file_size


class TTSGenerationError(Exception):
    """Raised when edge-tts fails to synthesize or save audio."""


async def generate_audio_core(
    text: str,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
    volume: str = DEFAULT_VOLUME,
) -> dict:
    """Synthesize `text` to an mp3 at `output_path` using edge-tts.

    Returns metadata about the resulting file. Raises TTSGenerationError
    on failure (network issues, invalid voice, empty output, etc.).
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
