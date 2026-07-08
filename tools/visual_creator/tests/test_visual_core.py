from __future__ import annotations

import base64
import io
import zipfile

import pytest

from tools.visual_creator.core import VisualCreatorError, generate_visuals_core


def _make_zip_base64(files: dict[str, str]) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return base64.b64encode(buf.getvalue()).decode()


def test_inline_code_entry_renders_without_zip(tmp_path):
    checklist = [
        {
            "path": "app/core/tts.py",
            "start_line": 5,
            "code": "def hello():\n    return 'hi'\n",
            "label": "hello function",
        }
    ]
    out = generate_visuals_core(checklist, zip_base64=None, persist_dir=tmp_path)
    assert len(out["files"]) == 1
    assert out["results"][0]["status"] == "OK"
    assert (tmp_path / out["files"][0]).exists()


def test_command_entry_renders_without_zip(tmp_path):
    checklist = [
        {"type": "command", "command": "pip install pygments", "output": "Successfully installed"}
    ]
    out = generate_visuals_core(checklist, zip_base64=None, persist_dir=tmp_path)
    assert len(out["files"]) == 1
    assert out["results"][0]["status"] == "OK"


def test_zip_lookup_entry_requires_zip_base64(tmp_path):
    checklist = [{"file": "main.py", "start_line": 1, "end_line": 2}]
    with pytest.raises(VisualCreatorError, match="zip_base64"):
        generate_visuals_core(checklist, zip_base64=None, persist_dir=tmp_path)


def test_zip_lookup_entry_renders_with_zip(tmp_path):
    zip_b64 = _make_zip_base64({"main.py": "def a():\n    pass\n\ndef b():\n    pass\n"})
    checklist = [{"file": "main.py", "start_line": 1, "end_line": 2, "label": "a func"}]
    out = generate_visuals_core(checklist, zip_base64=zip_b64, persist_dir=tmp_path)
    assert len(out["files"]) == 1
    assert out["results"][0]["status"] == "OK"


def test_invalid_theme_rejected(tmp_path):
    checklist = [{"path": "x.py", "code": "x = 1\n"}]
    with pytest.raises(VisualCreatorError, match="theme"):
        generate_visuals_core(checklist, zip_base64=None, persist_dir=tmp_path, theme="not-a-theme")


def test_invalid_base64_rejected(tmp_path):
    checklist = [{"file": "main.py", "start_line": 1, "end_line": 2}]
    with pytest.raises(VisualCreatorError, match="base64"):
        generate_visuals_core(checklist, zip_base64="not-valid-base64!!", persist_dir=tmp_path)


def test_repeat_calls_do_not_collide(tmp_path):
    checklist = [{"path": "x.py", "code": "x = 1\n", "label": "same label"}]
    out1 = generate_visuals_core(checklist, zip_base64=None, persist_dir=tmp_path)
    out2 = generate_visuals_core(checklist, zip_base64=None, persist_dir=tmp_path)
    assert out1["files"][0] != out2["files"][0]
    assert (tmp_path / out1["files"][0]).exists()
    assert (tmp_path / out2["files"][0]).exists()


def test_default_output_format_is_png_4k(tmp_path):
    """Default behavior (no output_format passed) now produces a 4K PNG."""
    from PIL import Image

    checklist = [{"path": "x.py", "code": "x = 1\n", "label": "default fmt"}]
    out = generate_visuals_core(checklist, zip_base64=None, persist_dir=tmp_path)
    assert len(out["files"]) == 1
    assert out["files"][0].endswith(".png")
    with Image.open(tmp_path / out["files"][0]) as img:
        assert max(img.size) >= 3840


def test_output_format_png_produces_valid_4k_png(tmp_path):
    from PIL import Image

    checklist = [{"path": "x.py", "code": "def hello():\n    return 'hi'\n", "label": "png test"}]
    out = generate_visuals_core(
        checklist, zip_base64=None, persist_dir=tmp_path, output_format="png"
    )
    assert out["results"][0]["status"] == "OK"
    assert len(out["files"]) == 1
    png_name = out["files"][0]
    assert png_name.endswith(".png")

    png_path = tmp_path / png_name
    assert png_path.exists()
    # No .svg should have been left behind in png-only mode.
    assert not list(tmp_path.glob("*.svg"))

    with Image.open(png_path) as img:
        assert img.format == "PNG"
        assert max(img.size) >= 3840


def test_output_format_both_produces_both_files(tmp_path):
    checklist = [{"path": "x.py", "code": "x = 1\n", "label": "both fmt"}]
    out = generate_visuals_core(
        checklist, zip_base64=None, persist_dir=tmp_path, output_format="both"
    )
    assert out["results"][0]["status"] == "OK"
    assert len(out["files"]) == 2
    suffixes = sorted(name.rsplit(".", 1)[-1] for name in out["files"])
    assert suffixes == ["png", "svg"]
    for name in out["files"]:
        assert (tmp_path / name).exists()


def test_invalid_output_format_rejected(tmp_path):
    checklist = [{"path": "x.py", "code": "x = 1\n"}]
    with pytest.raises(VisualCreatorError, match="output_format"):
        generate_visuals_core(
            checklist, zip_base64=None, persist_dir=tmp_path, output_format="jpeg"
        )


def test_cleanup_expired_visuals_sweeps_both_extensions(tmp_path, monkeypatch):
    import os
    import time

    from common import files as files_module

    monkeypatch.setattr(files_module, "VISUALS_DIR", tmp_path)

    svg_path = tmp_path / "old.svg"
    png_path = tmp_path / "old.png"
    svg_path.write_text("<svg></svg>")
    png_path.write_bytes(b"fake-png-bytes")

    old_time = time.time() - 10_000
    os.utime(svg_path, (old_time, old_time))
    os.utime(png_path, (old_time, old_time))

    removed = files_module.cleanup_expired_visuals(ttl_seconds=1)
    assert removed == 2
    assert not svg_path.exists()
    assert not png_path.exists()
