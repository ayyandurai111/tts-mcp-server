"""GET /api/v1/logs - recent request logs, for monitoring."""

from __future__ import annotations

from fastapi import APIRouter, Query

from common.logging import get_recent_logs

router = APIRouter(prefix="/api/v1", tags=["logs"])


@router.get("/logs")
async def get_logs(limit: int = Query(100, ge=1, le=1000)):
    return {"success": True, "logs": get_recent_logs(limit)}
