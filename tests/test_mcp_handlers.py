from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcp.handlers import handle_call_tool
from app.mcp.tools import handle_list_tools


@pytest.mark.asyncio
async def test_list_tools_exposes_single_voice_over_tool():
    tools = await handle_list_tools()
    assert len(tools) == 1
    assert tools[0].name == "voice_over"
    assert "text" in tools[0].inputSchema["properties"]


async def _fake_generate_audio_core(text, output_path: Path, **kwargs):
    output_path.write_bytes(b"fake-mp3-bytes")
    return {
        "file_path": str(output_path),
        "file_name": output_path.name,
        "file_size_bytes": output_path.stat().st_size,
        "file_size_human": "0.0 KB",
    }


@pytest.mark.asyncio
async def test_voice_over_tool_returns_content_and_filename():
    with patch("app.mcp.handlers.generate_audio_core", _fake_generate_audio_core):
        result = await handle_call_tool("voice_over", {"text": "hello there"})

    payload = json.loads(result[0].text)
    assert payload["success"] is True
    assert payload["content"] == "hello there"
    assert payload["filename"].endswith(".mp3")
    # Only content + filename (+ metadata) are returned, no local file_path leak
    assert "file_path" not in payload


@pytest.mark.asyncio
async def test_voice_over_tool_rejects_empty_text():
    result = await handle_call_tool("voice_over", {"text": "   "})
    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert "empty" in payload["error"].lower()


@pytest.mark.asyncio
async def test_voice_over_tool_handles_generation_failure():
    from app.core.tts import TTSGenerationError

    async def failing(*args, **kwargs):
        raise TTSGenerationError("synth failed")

    with patch("app.mcp.handlers.generate_audio_core", failing):
        result = await handle_call_tool("voice_over", {"text": "hello"})

    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert "synth failed" in payload["error"]


@pytest.mark.asyncio
async def test_unknown_tool_name_returns_error():
    result = await handle_call_tool("not_a_real_tool", {})
    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert "Unknown tool" in payload["error"]
