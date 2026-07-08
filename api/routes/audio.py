"""GET /api/v1/audio/{filename} - download/stream a generated MP3 from temp storage."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from common.files import resolve_temp_path

router = APIRouter(prefix="/api/v1", tags=["audio"])


@router.get("/audio/{filename}")
async def get_audio(filename: str):
    """Stream back a previously generated audio file by filename."""
    file_path = resolve_temp_path(filename)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Audio file '{filename}' not found. It may have expired "
                "or the server may have restarted (temp storage is ephemeral)."
            ),
        )
    return FileResponse(path=file_path, media_type="audio/mpeg", filename=file_path.name)
