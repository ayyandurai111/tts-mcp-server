from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_layer.registry import handle_call_tool
from mcp_layer.registry import handle_list_tools


@pytest.mark.asyncio
async def test_list_tools_exposes_voice_over_and_visual_creator():
    tools = await handle_list_tools()
    names = {t.name for t in tools}
    assert names == {"voice_over", "visual_creator", "video_renderer"}

    voice_over = next(t for t in tools if t.name == "voice_over")
    assert "text" in voice_over.inputSchema["properties"]

    visual_creator = next(t for t in tools if t.name == "visual_creator")
    assert "checklist" in visual_creator.inputSchema["properties"]
    assert visual_creator.inputSchema["required"] == ["checklist"]


async def _fake_generate_audio_core(text, output_path: Path, **kwargs):
    output_path.write_bytes(b"fake-mp3-bytes")
    return {
        "file_path": str(output_path),
        "file_name": output_path.name,
        "file_size_bytes": output_path.stat().st_size,
        "file_size_human": "0.0 KB",
        "duration_seconds": 2.5,
    }


@pytest.mark.asyncio
async def test_voice_over_tool_returns_content_and_filename():
    with patch("tools.voice_over.handler.generate_audio_core", _fake_generate_audio_core):
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
    from tools.voice_over.core import TTSGenerationError

    async def failing(*args, **kwargs):
        raise TTSGenerationError("synth failed")

    with patch("tools.voice_over.handler.generate_audio_core", failing):
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


@pytest.mark.asyncio
async def test_visual_creator_inline_code_entry_needs_no_zip(tmp_path):
    with patch("tools.visual_creator.handler.VISUALS_DIR", tmp_path):
        result = await handle_call_tool(
            "visual_creator",
            {
                "checklist": [
                    {
                        "path": "app/core/tts.py",
                        "start_line": 1,
                        "code": "def f():\n    return 1\n",
                        "label": "sample function",
                    }
                ]
            },
        )

    payload = json.loads(result[0].text)
    assert payload["success"] is True
    assert len(payload["files"]) == 1
    assert payload["files"][0].endswith(".png")
    assert (tmp_path / payload["files"][0]).exists()
    assert payload["results"][0]["status"] == "OK"


@pytest.mark.asyncio
async def test_visual_creator_requires_zip_for_zip_lookup_entry():
    result = await handle_call_tool(
        "visual_creator",
        {
            "checklist": [
                {"file": "app/core/tts.py", "start_line": 1, "end_line": 5}
            ]
        },
    )
    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert "zip_base64" in payload["error"]


@pytest.mark.asyncio
async def test_visual_creator_rejects_empty_checklist():
    result = await handle_call_tool("visual_creator", {"checklist": []})
    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert "checklist" in payload["error"].lower()


@pytest.mark.asyncio
async def test_visual_creator_tool_schema_exposes_output_format():
    tools = await handle_list_tools()
    visual_creator = next(t for t in tools if t.name == "visual_creator")
    output_format_schema = visual_creator.inputSchema["properties"]["output_format"]
    assert set(output_format_schema["enum"]) == {"svg", "png", "both"}
    assert output_format_schema["default"] == "png"


@pytest.mark.asyncio
async def test_visual_creator_output_format_png_passthrough(tmp_path):
    from PIL import Image

    with patch("tools.visual_creator.handler.VISUALS_DIR", tmp_path):
        result = await handle_call_tool(
            "visual_creator",
            {
                "checklist": [
                    {
                        "path": "app/core/tts.py",
                        "start_line": 1,
                        "code": "def f():\n    return 1\n",
                        "label": "png passthrough",
                    }
                ],
                "output_format": "png",
            },
        )

    payload = json.loads(result[0].text)
    assert payload["success"] is True
    assert len(payload["files"]) == 1
    assert payload["files"][0].endswith(".png")

    png_path = tmp_path / payload["files"][0]
    assert png_path.exists()
    with Image.open(png_path) as img:
        assert img.format == "PNG"
        assert max(img.size) >= 3840


# ---------------------------------------------------------------------------
# project_id / order sync (voice_over + visual_creator writing into a
# shared projects/{id}/order_{NN}/ folder)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voice_over_without_project_id_does_not_touch_project_store():
    with patch("tools.voice_over.handler.generate_audio_core", _fake_generate_audio_core):
        result = await handle_call_tool("voice_over", {"text": "hello there"})
    payload = json.loads(result[0].text)
    assert payload["success"] is True
    assert "project_id" not in payload
    assert "project_file" not in payload


@pytest.mark.asyncio
async def test_voice_over_with_project_id_requires_order():
    with patch("tools.voice_over.handler.generate_audio_core", _fake_generate_audio_core):
        result = await handle_call_tool(
            "voice_over", {"text": "hello there", "project_id": "demo-vlog"}
        )
    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert "order" in payload["error"].lower()


@pytest.mark.asyncio
async def test_voice_over_with_project_id_and_order_saves_to_project_store(tmp_path, monkeypatch):
    from common import project_store

    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path)

    with patch("tools.voice_over.handler.generate_audio_core", _fake_generate_audio_core):
        result = await handle_call_tool(
            "voice_over",
            {
                "text": "Now here's the interesting part.",
                "project_id": "demo-vlog",
                "order": 1,
                "label": "zip slip protection check",
            },
        )

    payload = json.loads(result[0].text)
    assert payload["success"] is True
    assert payload["project_id"] == "demo-vlog"
    assert payload["order"] == 1
    assert payload["duration_seconds"] == 2.5

    manifest = project_store.get_manifest("demo-vlog")
    assert len(manifest["orders"]) == 1
    order_1 = manifest["orders"][0]
    assert order_1["label"] == "zip slip protection check"
    assert order_1["script_text"] == "Now here's the interesting part."
    assert order_1["audio"]["filename"] == "audio.mp3"
    assert order_1["audio"]["duration_seconds"] == 2.5

    audio_file = project_store.order_dir("demo-vlog", 1) / "audio.mp3"
    assert audio_file.exists()


@pytest.mark.asyncio
async def test_visual_creator_with_project_id_saves_to_project_store(tmp_path, monkeypatch):
    from common import project_store

    projects_root = tmp_path / "projects"
    visuals_root = tmp_path / "visuals"
    monkeypatch.setattr(project_store, "PROJECTS_DIR", projects_root)

    with patch("tools.visual_creator.handler.VISUALS_DIR", visuals_root):
        result = await handle_call_tool(
            "visual_creator",
            {
                "checklist": [
                    {
                        "path": "app/core/tts.py",
                        "start_line": 1,
                        "code": "def f():\n    return 1\n",
                        "label": "zip slip protection check",
                    }
                ],
                "project_id": "demo-vlog",
            },
        )

    payload = json.loads(result[0].text)
    assert payload["success"] is True
    assert payload["project_id"] == "demo-vlog"
    assert payload["results"][0]["order"] == 1

    manifest = project_store.get_manifest("demo-vlog")
    order_1 = manifest["orders"][0]
    assert order_1["order"] == 1
    assert order_1["label"] == "zip slip protection check"
    assert order_1["visual"]["filenames"] == ["visual.png"]
    assert order_1["visual"]["width"] == 1920
    assert order_1["visual"]["height"] == 1080

    visual_file = project_store.order_dir("demo-vlog", 1) / "visual.png"
    assert visual_file.exists()


@pytest.mark.asyncio
async def test_voice_over_and_visual_creator_merge_into_same_order(tmp_path, monkeypatch):
    """The end-to-end scenario the sync tool depends on: calling voice_over
    and visual_creator separately for the same project_id/order results in
    one merged order entry with both audio and visual populated."""
    from common import project_store

    projects_root = tmp_path / "projects"
    visuals_root = tmp_path / "visuals"
    monkeypatch.setattr(project_store, "PROJECTS_DIR", projects_root)

    with patch("tools.voice_over.handler.generate_audio_core", _fake_generate_audio_core):
        await handle_call_tool(
            "voice_over",
            {
                "text": "Now here's the interesting part.",
                "project_id": "demo-vlog",
                "order": 1,
                "label": "zip slip protection check",
            },
        )

    with patch("tools.visual_creator.handler.VISUALS_DIR", visuals_root):
        await handle_call_tool(
            "visual_creator",
            {
                "checklist": [
                    {
                        "path": "app/core/tts.py",
                        "start_line": 1,
                        "code": "def f():\n    return 1\n",
                        "label": "zip slip protection check",
                    }
                ],
                "project_id": "demo-vlog",
            },
        )

    manifest = project_store.get_manifest("demo-vlog")
    assert len(manifest["orders"]) == 1
    order_1 = manifest["orders"][0]
    assert order_1["audio"]["filename"] == "audio.mp3"
    assert order_1["visual"]["filenames"] == ["visual.png"]
    assert order_1["label"] == "zip slip protection check"


# ---------------------------------------------------------------------------
# video_renderer
# ---------------------------------------------------------------------------

from tools.video_renderer.core import ffmpeg_available  # noqa: E402

requires_ffmpeg = pytest.mark.skipif(
    not ffmpeg_available(), reason="ffmpeg not available in this environment"
)


async def _real_audio_fake_generate_audio_core(text, output_path, **kwargs):
    """Unlike _fake_generate_audio_core (which just writes placeholder
    bytes), video_renderer's end-to-end tests shell out to real ffmpeg,
    which needs an actually-decodable MP3 - so this fake renders a short
    real sine-wave clip instead of stubbing the file out."""
    import subprocess

    from tools.video_renderer.core import FFMPEG_BINARY

    subprocess.run(
        [
            FFMPEG_BINARY, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
            "-c:a", "libmp3lame", str(output_path),
        ],
        capture_output=True, check=True,
    )
    return {
        "file_path": str(output_path),
        "file_name": output_path.name,
        "file_size_bytes": output_path.stat().st_size,
        "file_size_human": "0.0 KB",
        "duration_seconds": 1.0,
    }


async def _build_two_order_project(tmp_path, monkeypatch, project_id="demo-vlog"):
    """Real voice_over + visual_creator calls, isolated to tmp_path, giving
    a fully-populated 2-order project for video_renderer to render.

    visual_creator assigns each checklist entry's "order" by its position
    in the checklist array (see app/core/visual.py's ChecklistEntry
    parsing), so - matching how the tool is actually meant to be driven -
    both orders are submitted in a single checklist call rather than two
    separate single-item calls (which would otherwise both land on
    order=1)."""
    from common import project_store

    projects_root = tmp_path / "projects"
    visuals_root = tmp_path / "visuals"
    monkeypatch.setattr(project_store, "PROJECTS_DIR", projects_root)

    for order, label, text in (
        (1, "intro", "Welcome to the vlog."),
        (2, "outro", "Thanks for watching."),
    ):
        with patch("tools.voice_over.handler.generate_audio_core", _real_audio_fake_generate_audio_core):
            await handle_call_tool(
                "voice_over",
                {"text": text, "project_id": project_id, "order": order, "label": label},
            )

    with patch("tools.visual_creator.handler.VISUALS_DIR", visuals_root):
        await handle_call_tool(
            "visual_creator",
            {
                "checklist": [
                    {"type": "command", "command": "echo intro", "output": "ok", "label": "intro"},
                    {"type": "command", "command": "echo outro", "output": "ok", "label": "outro"},
                ],
                "project_id": project_id,
            },
        )
    return projects_root


@pytest.mark.asyncio
async def test_video_renderer_missing_project_id_is_a_tool_error():
    result = await handle_call_tool("video_renderer", {})
    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert "project_id" in payload["error"]


@pytest.mark.asyncio
async def test_video_renderer_unknown_project_is_a_tool_error(tmp_path, monkeypatch):
    from common import project_store

    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path / "projects")
    result = await handle_call_tool("video_renderer", {"project_id": "never-existed"})
    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert "never-existed" in payload["error"]


@pytest.mark.asyncio
async def test_video_renderer_rejects_bad_transition(tmp_path, monkeypatch):
    await _build_two_order_project(tmp_path, monkeypatch)
    result = await handle_call_tool(
        "video_renderer", {"project_id": "demo-vlog", "transition": "wipe"}
    )
    payload = json.loads(result[0].text)
    assert payload["success"] is False
    assert "transition" in payload["error"].lower()


@pytest.mark.asyncio
@requires_ffmpeg
async def test_video_renderer_end_to_end_via_handler(tmp_path, monkeypatch):
    """Full path: voice_over + visual_creator build a real 2-order project,
    then video_renderer renders it and save_final_video persists the MP4
    at projects/{project_id}/final_output.mp4."""
    from common import project_store

    await _build_two_order_project(tmp_path, monkeypatch)

    result = await handle_call_tool("video_renderer", {"project_id": "demo-vlog"})
    payload = json.loads(result[0].text)

    assert payload["success"] is True
    assert payload["filename"] == "final_output.mp4"
    assert payload["total_duration_seconds"] > 0
    assert len(payload["orders"]) == 2
    assert payload["warnings"] == []
    assert payload["download_url"] == "/api/v1/project/demo-vlog/video"

    final_path = project_store.final_video_path("demo-vlog")
    assert final_path.exists()
    assert final_path.stat().st_size > 0


@pytest.mark.asyncio
@requires_ffmpeg
async def test_video_renderer_surfaces_warnings_for_incomplete_orders(tmp_path, monkeypatch):
    from common import project_store

    projects_root = tmp_path / "projects"
    visuals_root = tmp_path / "visuals"
    monkeypatch.setattr(project_store, "PROJECTS_DIR", projects_root)

    # Only order 1 gets both audio and visual; order 2 gets audio only.
    with patch("tools.voice_over.handler.generate_audio_core", _real_audio_fake_generate_audio_core):
        await handle_call_tool(
            "voice_over",
            {"text": "Complete order.", "project_id": "demo-vlog", "order": 1, "label": "complete"},
        )
    with patch("tools.visual_creator.handler.VISUALS_DIR", visuals_root):
        await handle_call_tool(
            "visual_creator",
            {
                "checklist": [{"type": "command", "command": "echo hi", "output": "ok", "label": "complete"}],
                "project_id": "demo-vlog",
            },
        )
    with patch("tools.voice_over.handler.generate_audio_core", _real_audio_fake_generate_audio_core):
        await handle_call_tool(
            "voice_over",
            {"text": "Incomplete order.", "project_id": "demo-vlog", "order": 2, "label": "incomplete"},
        )

    result = await handle_call_tool("video_renderer", {"project_id": "demo-vlog"})
    payload = json.loads(result[0].text)

    assert payload["success"] is True
    assert len(payload["orders"]) == 1
    assert any("order 2" in w for w in payload["warnings"])
