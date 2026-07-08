from __future__ import annotations

import json
import time

import pytest

from common import project_store
from common.project_store import (
    ProjectStoreError,
    cleanup_expired_projects,
    final_video_path,
    get_manifest,
    list_projects,
    order_dir,
    project_dir,
    resolve_project_file,
    sanitize_project_id,
    save_audio_for_order,
    save_final_video,
    save_visual_for_order,
)


@pytest.fixture(autouse=True)
def _isolate_projects_dir(tmp_path, monkeypatch):
    """Every test gets its own PROJECTS_DIR so tests can't see each other's
    projects and nothing touches the real TEMP_DIR/projects on disk."""
    isolated = tmp_path / "projects"
    monkeypatch.setattr(project_store, "PROJECTS_DIR", isolated)
    yield isolated


def _make_audio_file(tmp_path, name="src_audio.mp3", content=b"fake-mp3-bytes"):
    p = tmp_path / name
    p.write_bytes(content)
    return p


def _make_visual_file(tmp_path, name="src_visual.png", content=b"fake-png-bytes"):
    p = tmp_path / name
    p.write_bytes(content)
    return p


# ---------------------------------------------------------------------------
# sanitize_project_id
# ---------------------------------------------------------------------------

def test_sanitize_project_id_keeps_safe_chars():
    assert sanitize_project_id("my-vlog_01") == "my-vlog_01"


def test_sanitize_project_id_strips_unsafe_chars():
    assert sanitize_project_id("my vlog!! /weird") == "my_vlog_weird"


def test_sanitize_project_id_rejects_empty():
    with pytest.raises(ProjectStoreError):
        sanitize_project_id("")
    with pytest.raises(ProjectStoreError):
        sanitize_project_id("   ")


def test_sanitize_project_id_blocks_path_traversal():
    cleaned = sanitize_project_id("../../etc/passwd")
    assert ".." not in cleaned
    assert "/" not in cleaned


# ---------------------------------------------------------------------------
# save_audio_for_order / save_visual_for_order
# ---------------------------------------------------------------------------

def test_save_audio_for_order_copies_file_and_writes_meta(tmp_path):
    src = _make_audio_file(tmp_path)
    meta = save_audio_for_order(
        "demo-project", 1, src, label="intro", script_text="hello there",
        duration_seconds=3.21,
    )

    assert meta["order"] == 1
    assert meta["label"] == "intro"
    assert meta["script_text"] == "hello there"
    assert meta["audio"]["filename"] == "audio.mp3"
    assert meta["audio"]["duration_seconds"] == 3.21

    dest = order_dir("demo-project", 1) / "audio.mp3"
    assert dest.exists()
    assert dest.read_bytes() == src.read_bytes()


def test_save_visual_for_order_single_file(tmp_path):
    src = _make_visual_file(tmp_path)
    meta = save_visual_for_order(
        "demo-project", 1, [src], label="zip slip check", width=3840, height=2160,
    )

    assert meta["visual"]["filenames"] == ["visual.png"]
    assert meta["visual"]["width"] == 3840
    assert meta["visual"]["height"] == 2160

    dest = order_dir("demo-project", 1) / "visual.png"
    assert dest.exists()


def test_save_visual_for_order_multiple_pages(tmp_path):
    src1 = _make_visual_file(tmp_path, "p1.png", b"page1")
    src2 = _make_visual_file(tmp_path, "p2.png", b"page2")
    meta = save_visual_for_order("demo-project", 2, [src1, src2], label="long file")

    assert meta["visual"]["filenames"] == ["visual_p1.png", "visual_p2.png"]
    assert (order_dir("demo-project", 2) / "visual_p1.png").read_bytes() == b"page1"
    assert (order_dir("demo-project", 2) / "visual_p2.png").read_bytes() == b"page2"


def test_save_visual_for_order_requires_at_least_one_path():
    with pytest.raises(ProjectStoreError):
        save_visual_for_order("demo-project", 1, [])


def test_audio_and_visual_for_same_order_merge_not_overwrite(tmp_path):
    """Saving audio then visual for the same order should leave both keys
    populated in that order's meta - this is the core guarantee that makes
    sync possible when the two tools are called independently."""
    audio_src = _make_audio_file(tmp_path)
    visual_src = _make_visual_file(tmp_path)

    save_audio_for_order("demo-project", 1, audio_src, label="intro",
                          script_text="hi", duration_seconds=4.0)
    meta = save_visual_for_order("demo-project", 1, [visual_src], label="intro")

    assert meta["audio"]["filename"] == "audio.mp3"
    assert meta["audio"]["duration_seconds"] == 4.0
    assert meta["visual"]["filenames"] == ["visual.png"]
    assert meta["script_text"] == "hi"


def test_save_rejects_negative_order(tmp_path):
    src = _make_audio_file(tmp_path)
    with pytest.raises(ProjectStoreError):
        save_audio_for_order("demo-project", -1, src)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def test_manifest_reflects_all_orders_sorted(tmp_path):
    a1 = _make_audio_file(tmp_path, "a1.mp3", b"1")
    a2 = _make_audio_file(tmp_path, "a2.mp3", b"2")

    save_audio_for_order("demo-project", 2, a2, label="second", duration_seconds=2.0)
    save_audio_for_order("demo-project", 1, a1, label="first", duration_seconds=1.0)

    manifest = get_manifest("demo-project")
    assert manifest["project_id"] == "demo-project"
    assert [o["order"] for o in manifest["orders"]] == [1, 2]
    assert manifest["orders"][0]["label"] == "first"
    assert manifest["orders"][1]["label"] == "second"


def test_manifest_file_written_to_disk(tmp_path):
    src = _make_audio_file(tmp_path)
    save_audio_for_order("demo-project", 1, src, duration_seconds=1.0)

    manifest_file = project_dir("demo-project") / "manifest.json"
    assert manifest_file.exists()
    with open(manifest_file) as f:
        data = json.load(f)
    assert data["orders"][0]["order"] == 1


def test_get_manifest_for_project_with_no_saves_builds_empty(tmp_path):
    # project_dir doesn't exist on disk yet - get_manifest should still
    # return a well-formed (empty) manifest rather than raising.
    manifest = get_manifest("never-touched")
    assert manifest["orders"] == []


def test_list_projects(tmp_path):
    a1 = _make_audio_file(tmp_path, "a1.mp3")
    a2 = _make_audio_file(tmp_path, "a2.mp3")
    save_audio_for_order("proj-a", 1, a1, duration_seconds=1.0)
    save_audio_for_order("proj-b", 1, a2, duration_seconds=1.0)

    assert set(list_projects()) == {"proj-a", "proj-b"}


# ---------------------------------------------------------------------------
# resolve_project_file
# ---------------------------------------------------------------------------

def test_resolve_project_file_returns_expected_path(tmp_path):
    src = _make_audio_file(tmp_path)
    save_audio_for_order("demo-project", 1, src, duration_seconds=1.0)

    resolved = resolve_project_file("demo-project", 1, "audio.mp3")
    assert resolved.exists()
    assert resolved.name == "audio.mp3"


def test_resolve_project_file_blocks_traversal(tmp_path):
    src = _make_audio_file(tmp_path)
    save_audio_for_order("demo-project", 1, src, duration_seconds=1.0)

    # Even a maliciously crafted filename can only resolve to its basename
    # within the order dir - it can never escape via '..' segments.
    resolved = resolve_project_file("demo-project", 1, "../../../etc/passwd")
    assert resolved.parent == order_dir("demo-project", 1)


# ---------------------------------------------------------------------------
# cleanup_expired_projects
# ---------------------------------------------------------------------------

def test_cleanup_expired_projects_removes_old_and_keeps_fresh(tmp_path):
    old_src = _make_audio_file(tmp_path, "old.mp3")
    fresh_src = _make_audio_file(tmp_path, "fresh.mp3")

    save_audio_for_order("old-project", 1, old_src, duration_seconds=1.0)
    save_audio_for_order("fresh-project", 1, fresh_src, duration_seconds=1.0)

    old_manifest = project_dir("old-project") / "manifest.json"
    old_time = time.time() - 999999
    import os
    os.utime(old_manifest, (old_time, old_time))

    removed = cleanup_expired_projects(ttl_seconds=3600)
    assert removed == 1
    assert not project_dir("old-project").exists()
    assert project_dir("fresh-project").exists()


# ---------------------------------------------------------------------------
# save_final_video / final_video_path (video_renderer output)
# ---------------------------------------------------------------------------

def test_save_final_video_copies_to_project_root(tmp_path):
    src = tmp_path / "rendered.mp4"
    src.write_bytes(b"fake-mp4-bytes")

    dest = save_final_video("demo-project", src)

    assert dest == final_video_path("demo-project")
    assert dest.parent == project_dir("demo-project")
    assert dest.name == "final_output.mp4"
    assert dest.read_bytes() == b"fake-mp4-bytes"


def test_save_final_video_raises_when_source_missing(tmp_path):
    missing_src = tmp_path / "does_not_exist.mp4"
    with pytest.raises(ProjectStoreError, match="does not exist"):
        save_final_video("demo-project", missing_src)


def test_save_final_video_overwrites_previous_render(tmp_path):
    src1 = tmp_path / "v1.mp4"
    src1.write_bytes(b"first-render")
    save_final_video("demo-project", src1)

    src2 = tmp_path / "v2.mp4"
    src2.write_bytes(b"second-render")
    dest = save_final_video("demo-project", src2)

    assert dest.read_bytes() == b"second-render"


def test_final_video_path_before_render_does_not_exist(tmp_path):
    path = final_video_path("brand-new-project")
    assert not path.exists()
    assert path.name == "final_output.mp4"
