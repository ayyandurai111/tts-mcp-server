"""Lightweight in-memory request log, used for the /api/v1/logs endpoint."""

from __future__ import annotations

from app.config import MAX_LOG_ENTRIES
from app.utils.formatting import utc_now_iso

request_log: list[dict] = []


def log_request(tool: str, params: dict, result: dict) -> None:
    """Record a request/response pair, redacting long text fields."""
    entry = {
        "tool": tool,
        "params": {
            k: v for k, v in params.items() if k != "text" or len(str(v)) < 100
        },
        "success": bool(result.get("success", False)),
        "timestamp": utc_now_iso(),
    }
    request_log.append(entry)
    if len(request_log) > MAX_LOG_ENTRIES:
        request_log.pop(0)


def get_recent_logs(limit: int = 100) -> list[dict]:
    return request_log[-limit:]
