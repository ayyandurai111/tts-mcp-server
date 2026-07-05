from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core.tts import TTSGenerationError, generate_audio_core, list_available_voices


class FakeCommunicate:
    def __init__(self, *args, **kwargs):
        pass

    async def save(self, path: str):
        Path(path).write_bytes(b"fake-mp3-bytes")


@pytest.mark.asyncio
async def test_generate_audio_core_writes_file(tmp_path):
    out = tmp_path / "out.mp3"
    with patch("app.core.tts.edge_tts.Communicate", FakeCommunicate):
        info = await generate_audio_core("hello", out, voice="en-US-GuyNeural")

    assert out.exists()
    assert info["file_name"] == "out.mp3"
    assert info["file_size_bytes"] > 0


@pytest.mark.asyncio
async def test_generate_audio_core_raises_on_failure(tmp_path):
    out = tmp_path / "out.mp3"

    class BrokenCommunicate:
        def __init__(self, *args, **kwargs):
            pass

        async def save(self, path: str):
            raise RuntimeError("network down")

    with patch("app.core.tts.edge_tts.Communicate", BrokenCommunicate):
        with pytest.raises(TTSGenerationError):
            await generate_audio_core("hello", out)


@pytest.mark.asyncio
async def test_generate_audio_core_raises_on_empty_output(tmp_path):
    out = tmp_path / "out.mp3"

    class EmptyCommunicate:
        def __init__(self, *args, **kwargs):
            pass

        async def save(self, path: str):
            Path(path).write_bytes(b"")

    with patch("app.core.tts.edge_tts.Communicate", EmptyCommunicate):
        with pytest.raises(TTSGenerationError):
            await generate_audio_core("hello", out)


@pytest.mark.asyncio
async def test_list_available_voices_filters(monkeypatch):
    fake_voices = [
        {"ShortName": "en-US-GuyNeural", "Locale": "en-US", "Gender": "Male"},
        {"ShortName": "en-IN-PrabhatNeural", "Locale": "en-IN", "Gender": "Male"},
        {"ShortName": "hi-IN-SwaraNeural", "Locale": "hi-IN", "Gender": "Female"},
    ]

    async def fake_list_voices():
        return fake_voices

    with patch("app.core.tts.edge_tts.list_voices", fake_list_voices):
        voices = await list_available_voices(language="en")

    assert len(voices) == 2
    assert all(v["locale"].startswith("en") for v in voices)
