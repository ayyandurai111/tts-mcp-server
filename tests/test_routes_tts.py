from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


async def _fake_generate_audio_core(text, output_path: Path, **kwargs):
    output_path.write_bytes(b"fake-mp3-bytes")
    return {
        "file_path": str(output_path),
        "file_name": output_path.name,
        "file_size_bytes": output_path.stat().st_size,
        "file_size_human": "0.0 KB",
    }


@pytest.mark.asyncio
async def test_rest_tts_success(client):
    with patch("app.routes.tts.generate_audio_core", _fake_generate_audio_core):
        resp = await client.post("/api/v1/tts", json={"text": "hello world"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["content"] == "hello world"
    assert body["audio"]["filename"].endswith(".mp3")
    assert body["audio"]["url"].startswith("/api/v1/audio/")


@pytest.mark.asyncio
async def test_rest_tts_empty_text_rejected(client):
    resp = await client.post("/api/v1/tts", json={"text": ""})
    assert resp.status_code == 422  # pydantic min_length validation


@pytest.mark.asyncio
async def test_rest_tts_generation_failure_returns_502(client):
    from app.core.tts import TTSGenerationError

    async def failing(*args, **kwargs):
        raise TTSGenerationError("boom")

    with patch("app.routes.tts.generate_audio_core", failing):
        resp = await client.post("/api/v1/tts", json={"text": "hello"})

    assert resp.status_code == 502
    assert "boom" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_download_generated_audio(client, tmp_path):
    with patch("app.routes.tts.generate_audio_core", _fake_generate_audio_core):
        resp = await client.post(
            "/api/v1/tts", json={"text": "download me", "output_filename": "clip1"}
        )
    filename = resp.json()["audio"]["filename"]

    dl = await client.get(f"/api/v1/audio/{filename}")
    assert dl.status_code == 200
    assert dl.content == b"fake-mp3-bytes"


@pytest.mark.asyncio
async def test_download_missing_audio_404(client):
    resp = await client.get("/api/v1/audio/does-not-exist.mp3")
    assert resp.status_code == 404
