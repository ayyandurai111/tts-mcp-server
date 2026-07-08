from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.video_renderer import core as render_mod
from tools.video_renderer.core import (
    VideoRenderError,
    build_render_plan,
    ffmpeg_available,
    render_project_video,
)

FFMPEG_AVAILABLE = ffmpeg_available()
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG_AVAILABLE, reason="ffmpeg not available in this environment"
)


def _order_entry(order, label="beat", duration=2.0, filenames=("visual.png",), width=1920, height=1080):
    return {
        "order": order,
        "label": label,
        "audio": {"filename": "audio.mp3", "duration_seconds": duration},
        "visual": {"filenames": list(filenames), "width": width, "height": height},
    }


def _manifest(orders, project_id="demo"):
    return {"project_id": project_id, "orders": orders}


# ---------------------------------------------------------------------------
# build_render_plan - manifest -> segments (no ffmpeg needed)
# ---------------------------------------------------------------------------

def test_build_render_plan_happy_path(tmp_path, monkeypatch):
    for n in (1, 2):
        d = tmp_path / f"order_{n:02d}"
        d.mkdir()
        (d / "audio.mp3").write_bytes(b"fake")
        (d / "visual.png").write_bytes(b"fake")

    monkeypatch.setattr(
        render_mod, "order_dir", lambda pid, order: tmp_path / f"order_{order:02d}", raising=False
    )
    # build_render_plan imports order_dir locally from project_store, so patch there instead.
    import common.project_store as ps
    monkeypatch.setattr(ps, "order_dir", lambda pid, order: tmp_path / f"order_{order:02d}")

    manifest = _manifest([_order_entry(1), _order_entry(2)])
    segments, warnings = build_render_plan(manifest)

    assert warnings == []
    assert [s["order"] for s in segments] == [1, 2]
    assert segments[0]["pages"][0]["duration_seconds"] == 2.0


def test_build_render_plan_skips_orders_missing_audio_or_visual(tmp_path, monkeypatch):
    for n in (1, 2, 3):
        d = tmp_path / f"order_{n:02d}"
        d.mkdir()
        (d / "audio.mp3").write_bytes(b"fake")
        (d / "visual.png").write_bytes(b"fake")

    import common.project_store as ps
    monkeypatch.setattr(ps, "order_dir", lambda pid, order: tmp_path / f"order_{order:02d}")

    orders = [
        _order_entry(1),
        {"order": 2, "label": "no audio", "audio": None,
         "visual": {"filenames": ["visual.png"], "width": 1920, "height": 1080}},
        {"order": 3, "label": "no visual", "audio": {"filename": "audio.mp3", "duration_seconds": 1.0},
         "visual": None},
    ]
    segments, warnings = build_render_plan(_manifest(orders))

    assert [s["order"] for s in segments] == [1]
    assert any("order 2" in w and "audio" in w for w in warnings)
    assert any("order 3" in w and "visual" in w for w in warnings)


def test_build_render_plan_raises_when_no_renderable_orders():
    orders = [{"order": 1, "label": "x", "audio": None, "visual": None}]
    with pytest.raises(VideoRenderError, match="no renderable orders"):
        build_render_plan(_manifest(orders))


def test_build_render_plan_raises_on_empty_manifest():
    with pytest.raises(VideoRenderError, match="no orders"):
        build_render_plan(_manifest([]))


def test_build_render_plan_requires_uniform_resolution(tmp_path, monkeypatch):
    for n in (1, 2):
        d = tmp_path / f"order_{n:02d}"
        d.mkdir()
        (d / "audio.mp3").write_bytes(b"fake")
        (d / "visual.png").write_bytes(b"fake")

    import common.project_store as ps
    monkeypatch.setattr(ps, "order_dir", lambda pid, order: tmp_path / f"order_{order:02d}")

    orders = [
        _order_entry(1, width=1920, height=1080),
        _order_entry(2, width=1280, height=720),
    ]
    with pytest.raises(VideoRenderError, match="resolution"):
        build_render_plan(_manifest(orders))


def test_build_render_plan_splits_pagination_duration_evenly(tmp_path, monkeypatch):
    d = tmp_path / "order_01"
    d.mkdir()
    (d / "audio.mp3").write_bytes(b"fake")
    (d / "visual_p1.png").write_bytes(b"fake")
    (d / "visual_p2.png").write_bytes(b"fake")

    import common.project_store as ps
    monkeypatch.setattr(ps, "order_dir", lambda pid, order: tmp_path / f"order_{order:02d}")

    orders = [_order_entry(1, duration=5.0, filenames=("visual_p1.png", "visual_p2.png"))]
    segments, warnings = build_render_plan(_manifest(orders))

    assert warnings == []
    pages = segments[0]["pages"]
    assert len(pages) == 2
    assert pages[0]["duration_seconds"] == pytest.approx(2.5)
    assert pages[1]["duration_seconds"] == pytest.approx(2.5)


def test_build_render_plan_raises_when_file_missing_on_disk(tmp_path, monkeypatch):
    d = tmp_path / "order_01"
    d.mkdir()
    (d / "audio.mp3").write_bytes(b"fake")
    # visual.png intentionally not created

    import common.project_store as ps
    monkeypatch.setattr(ps, "order_dir", lambda pid, order: tmp_path / f"order_{order:02d}")

    with pytest.raises(VideoRenderError, match="not found on disk"):
        build_render_plan(_manifest([_order_entry(1)]))


# ---------------------------------------------------------------------------
# ffmpeg command construction - mocked subprocess.run
# ---------------------------------------------------------------------------

def test_run_ffmpeg_raises_when_binary_unavailable(monkeypatch):
    monkeypatch.setattr(render_mod, "ffmpeg_available", lambda: False)
    with pytest.raises(VideoRenderError, match="ffmpeg is not available"):
        render_mod._run_ffmpeg(["-version"], step="test step")


def test_run_ffmpeg_raises_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(render_mod, "ffmpeg_available", lambda: True)

    class FakeProc:
        returncode = 1
        stdout = b""
        stderr = b"boom: invalid input"

    with patch("subprocess.run", return_value=FakeProc()):
        with pytest.raises(VideoRenderError, match="boom: invalid input"):
            render_mod._run_ffmpeg(["-i", "bad"], step="render order 1")


def test_run_ffmpeg_raises_on_timeout(monkeypatch):
    monkeypatch.setattr(render_mod, "ffmpeg_available", lambda: True)

    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1)

    with patch("subprocess.run", side_effect=_raise_timeout):
        with pytest.raises(VideoRenderError, match="timed out"):
            render_mod._run_ffmpeg(["-i", "x"], step="render order 1")


def test_render_project_video_rejects_invalid_transition():
    with pytest.raises(VideoRenderError, match="Invalid transition"):
        render_project_video(_manifest([_order_entry(1)]), Path("/tmp/out.mp4"), transition="wipe")


def test_render_project_video_raises_when_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr(render_mod, "ffmpeg_available", lambda: False)
    with pytest.raises(VideoRenderError, match="ffmpeg is not available"):
        render_project_video(_manifest([_order_entry(1)]), Path("/tmp/out.mp4"))


# ---------------------------------------------------------------------------
# Real end-to-end render (only if ffmpeg is actually available)
# ---------------------------------------------------------------------------

def _make_test_assets(base_dir: Path, durations: dict[int, float]):
    """Create real tiny PNGs + silent MP3s for `order` -> `duration_seconds`."""
    from PIL import Image

    for order, duration in durations.items():
        d = base_dir / f"order_{order:02d}"
        d.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (320, 180), (10 * order, 20, 30)).save(d / "visual.png")
        subprocess.run(
            [
                render_mod.FFMPEG_BINARY, "-y", "-f", "lavfi",
                "-i", f"sine=frequency=440:duration={duration}",
                "-c:a", "libmp3lame", str(d / "audio.mp3"),
            ],
            capture_output=True, check=True,
        )


@requires_ffmpeg
def test_real_render_cut_transition_produces_playable_mp4(tmp_path, monkeypatch):
    _make_test_assets(tmp_path, {1: 1.0, 2: 0.8})

    import common.project_store as ps
    monkeypatch.setattr(ps, "order_dir", lambda pid, order: tmp_path / f"order_{order:02d}")

    orders = [
        _order_entry(1, duration=1.0, width=320, height=180),
        _order_entry(2, duration=0.8, width=320, height=180),
    ]
    out_path = tmp_path / "final.mp4"
    result = render_project_video(_manifest(orders), out_path, transition="cut")

    assert out_path.exists()
    assert out_path.stat().st_size > 0
    assert result["total_duration_seconds"] == pytest.approx(1.8, abs=0.05)
    assert result["warnings"] == []
    assert [o["status"] for o in result["orders"]] == ["rendered", "rendered"]


@requires_ffmpeg
def test_real_render_skips_incomplete_orders_with_warning(tmp_path, monkeypatch):
    _make_test_assets(tmp_path, {1: 1.0})
    # order 2 has no assets at all -> missing audio + visual

    import common.project_store as ps
    monkeypatch.setattr(ps, "order_dir", lambda pid, order: tmp_path / f"order_{order:02d}")

    orders = [
        _order_entry(1, duration=1.0, width=320, height=180),
        {"order": 2, "label": "incomplete", "audio": None, "visual": None},
    ]
    out_path = tmp_path / "final.mp4"
    result = render_project_video(_manifest(orders), out_path, transition="cut")

    assert out_path.exists()
    assert len(result["orders"]) == 1
    assert any("order 2" in w for w in result["warnings"])


@requires_ffmpeg
def test_real_render_paginated_visual(tmp_path, monkeypatch):
    from PIL import Image

    d = tmp_path / "order_01"
    d.mkdir(parents=True)
    Image.new("RGB", (320, 180), (10, 20, 30)).save(d / "visual_p1.png")
    Image.new("RGB", (320, 180), (30, 20, 10)).save(d / "visual_p2.png")
    subprocess.run(
        [render_mod.FFMPEG_BINARY, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0",
         "-c:a", "libmp3lame", str(d / "audio.mp3")],
        capture_output=True, check=True,
    )

    import common.project_store as ps
    monkeypatch.setattr(ps, "order_dir", lambda pid, order: tmp_path / f"order_{order:02d}")

    orders = [_order_entry(1, duration=2.0, filenames=("visual_p1.png", "visual_p2.png"), width=320, height=180)]
    out_path = tmp_path / "final.mp4"
    result = render_project_video(_manifest(orders), out_path, transition="cut")

    assert out_path.exists()
    assert result["orders"][0]["pages"] == 2
    assert result["total_duration_seconds"] == pytest.approx(2.0, abs=0.05)


@requires_ffmpeg
def test_real_render_crossfade_shortens_total_duration(tmp_path, monkeypatch):
    _make_test_assets(tmp_path, {1: 2.0, 2: 2.0})

    import common.project_store as ps
    monkeypatch.setattr(ps, "order_dir", lambda pid, order: tmp_path / f"order_{order:02d}")

    orders = [
        _order_entry(1, duration=2.0, width=320, height=180),
        _order_entry(2, duration=2.0, width=320, height=180),
    ]
    out_path = tmp_path / "final_xfade.mp4"
    result = render_project_video(
        _manifest(orders), out_path, transition="crossfade", crossfade_seconds=0.5
    )

    assert out_path.exists()
    # 2.0 + 2.0 - 0.5 overlap = 3.5
    assert result["total_duration_seconds"] == pytest.approx(3.5, abs=0.1)
