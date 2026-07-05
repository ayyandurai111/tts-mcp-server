from __future__ import annotations

from app.core.files import generate_filename, resolve_temp_path, sanitize_filename
from app.config import TEMP_DIR


def test_generate_filename_default_ends_with_mp3():
    name = generate_filename("hello world", "en-US-GuyNeural")
    assert name.endswith(".mp3")
    assert "en_US_GuyNeural" in name


def test_generate_filename_custom_name_appends_extension():
    name = generate_filename("hi", "en-US-GuyNeural", custom_name="my_clip")
    assert name == "my_clip.mp3"


def test_generate_filename_custom_name_keeps_existing_extension():
    name = generate_filename("hi", "en-US-GuyNeural", custom_name="my_clip.mp3")
    assert name == "my_clip.mp3"


def test_sanitize_filename_strips_unsafe_chars():
    assert sanitize_filename("../../etc/passwd") == "etc_passwd"
    assert sanitize_filename("weird name!.mp3") == "weird_name_.mp3"


def test_resolve_temp_path_prevents_traversal():
    path = resolve_temp_path("../../etc/passwd")
    assert path.parent == TEMP_DIR
    assert path.name == "passwd"


def test_two_generated_filenames_are_unique():
    a = generate_filename("same text", "en-US-GuyNeural")
    b = generate_filename("same text", "en-US-GuyNeural")
    assert a != b
