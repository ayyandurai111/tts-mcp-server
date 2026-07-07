"""GET /api/v1/visual/{filename} - download a generated SVG screenshot from temp storage."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.files import resolve_visual_path

router = APIRouter(prefix="/api/v1", tags=["visuals"])


@router.get("/visual/{filename}")
async def get_visual(filename: str):
    """Stream back a previously generated SVG screenshot by filename."""
    file_path = resolve_visual_path(filename)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Visual '{filename}' not found. It may have expired or the "
                "server may have restarted (temp storage is ephemeral)."
            ),
        )
    return FileResponse(path=file_path, media_type="image/svg+xml", filename=file_path.name)
