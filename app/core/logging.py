"""Lightweight in-memory request log, used for the /api/v1/logs endpoint."""

from __future__ import annotations

from app.config import MAX_LOG_ENTRIES
from app.utils.formatting import utc_now_iso

request_log: list[dict] = []


_MAX_PARAM_LEN = 100


def _redact_long(value):
    """Replace any large field (long text, base64 blobs, big checklists) with a marker."""
    text = str(value)
    if len(text) < _MAX_PARAM_LEN:
        return value
    return f"<redacted: {len(text)} chars>"


def log_request(tool: str, params: dict, result: dict) -> None:
    """Record a request/response pair, redacting large field values."""
    entry = {
        "tool": tool,
        "params": {k: _redact_long(v) for k, v in params.items()},
        "success": bool(result.get("success", False)),
        "timestamp": utc_now_iso(),
    }
    request_log.append(entry)
    if len(request_log) > MAX_LOG_ENTRIES:
        request_log.pop(0)


def get_recent_logs(limit: int = 100) -> list[dict]:
    return request_log[-limit:]
