from __future__ import annotations

import pytest

from common import project_store


@pytest.fixture(autouse=True)
def _isolate_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path)
    yield tmp_path


@pytest.mark.asyncio
async def test_get_projects_lists_known_projects(client):
    src = project_store.PROJECTS_DIR.parent / "a1.mp3"
    src.write_bytes(b"x")
    project_store.save_audio_for_order("proj-a", 1, src, duration_seconds=1.0)

    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert resp.json()["projects"] == ["proj-a"]


@pytest.mark.asyncio
async def test_get_project_manifest_unknown_project_404(client):
    resp = await client.get("/api/v1/project/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_project_manifest_returns_orders(client):
    src = project_store.PROJECTS_DIR.parent / "a1.mp3"
    src.write_bytes(b"x")
    project_store.save_audio_for_order(
        "demo-vlog", 1, src, label="intro", script_text="hi", duration_seconds=3.5
    )

    resp = await client.get("/api/v1/project/demo-vlog")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "demo-vlog"
    assert body["orders"][0]["label"] == "intro"
    assert body["orders"][0]["audio"]["duration_seconds"] == 3.5


@pytest.mark.asyncio
async def test_get_project_file_downloads_audio(client):
    src = project_store.PROJECTS_DIR.parent / "a1.mp3"
    src.write_bytes(b"fake-mp3-bytes")
    project_store.save_audio_for_order("demo-vlog", 1, src, duration_seconds=1.0)

    resp = await client.get("/api/v1/project/demo-vlog/1/audio.mp3")
    assert resp.status_code == 200
    assert resp.content == b"fake-mp3-bytes"
    assert resp.headers["content-type"] == "audio/mpeg"


@pytest.mark.asyncio
async def test_get_project_file_missing_file_404(client):
    src = project_store.PROJECTS_DIR.parent / "a1.mp3"
    src.write_bytes(b"x")
    project_store.save_audio_for_order("demo-vlog", 1, src, duration_seconds=1.0)

    resp = await client.get("/api/v1/project/demo-vlog/1/visual.png")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_project_video_404_before_render(client):
    """No video route conflict with /{order}/{filename}: 'video' isn't
    parsed as an int order, so this must 404 as "no video yet", not as a
    route-mismatch/422."""
    src = project_store.PROJECTS_DIR.parent / "a1.mp3"
    src.write_bytes(b"x")
    project_store.save_audio_for_order("demo-vlog", 1, src, duration_seconds=1.0)

    resp = await client.get("/api/v1/project/demo-vlog/video")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_project_video_downloads_after_render(client):
    src = project_store.PROJECTS_DIR.parent / "a1.mp3"
    src.write_bytes(b"x")
    project_store.save_audio_for_order("demo-vlog", 1, src, duration_seconds=1.0)

    final_src = project_store.PROJECTS_DIR.parent / "rendered.mp4"
    final_src.write_bytes(b"fake-mp4-bytes")
    project_store.save_final_video("demo-vlog", final_src)

    resp = await client.get("/api/v1/project/demo-vlog/video")
    assert resp.status_code == 200
    assert resp.content == b"fake-mp4-bytes"
    assert resp.headers["content-type"] == "video/mp4"
