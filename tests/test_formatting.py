from __future__ import annotations

from common.formatting import human_file_size, utc_now_iso


def test_human_file_size_kb():
    assert human_file_size(2048) == "2.0 KB"


def test_human_file_size_mb():
    assert human_file_size(5 * 1024 * 1024) == "5.00 MB"


def test_utc_now_iso_format():
    ts = utc_now_iso()
    assert ts.endswith("Z")
    assert "T" in ts
