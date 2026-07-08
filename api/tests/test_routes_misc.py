from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_root_endpoint(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "VoiceOver MCP Server"
    assert "endpoints" in body


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "temp_dir" in body


@pytest.mark.asyncio
async def test_voices_endpoint(client):
    fake_voices = [
        {"name": "en-US-GuyNeural", "locale": "en-US", "gender": "Male", "friendly_name": "Guy"},
    ]

    async def fake_list(*args, **kwargs):
        return fake_voices

    with patch("api.routes.voices.list_available_voices", fake_list):
        resp = await client.get("/api/v1/voices?language=en")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["count"] == 1


@pytest.mark.asyncio
async def test_logs_endpoint(client):
    resp = await client.get("/api/v1/logs")
    assert resp.status_code == 200
    assert "logs" in resp.json()
