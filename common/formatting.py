"""Small, dependency-free formatting helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def human_file_size(num_bytes: int) -> str:
    """Format a byte count as a short human-readable string."""
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with a trailing 'Z'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
