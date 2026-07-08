"""GET /api/v1/visual/{filename} - download a generated SVG or PNG screenshot from temp storage."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from common.files import resolve_visual_path

router = APIRouter(prefix="/api/v1", tags=["visuals"])

_MEDIA_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
}
_DEFAULT_MEDIA_TYPE = "application/octet-stream"


@router.get("/visual/{filename}")
async def get_visual(filename: str):
    """Stream back a previously generated SVG or PNG screenshot by filename."""
    file_path = resolve_visual_path(filename)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Visual '{filename}' not found. It may have expired or the "
                "server may have restarted (temp storage is ephemeral)."
            ),
        )
    media_type = _MEDIA_TYPES.get(file_path.suffix.lower(), _DEFAULT_MEDIA_TYPE)
    return FileResponse(path=file_path, media_type=media_type, filename=file_path.name)
