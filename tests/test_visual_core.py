from __future__ import annotations

import base64
import io
import zipfile

import pytest

from app.core.visual import VisualCreatorError, generate_visuals_core


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
