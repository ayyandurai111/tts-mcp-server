"""GET /api/v1/voices - list available edge-tts voices."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from tools.voice_over.core import list_available_voices

router = APIRouter(prefix="/api/v1", tags=["voices"])


@router.get("/voices")
async def rest_voices(
    language: Optional[str] = Query(None, description="Filter by language code, e.g. 'en', 'hi'"),
    gender: Optional[str] = Query(None, description="Filter by 'Male' or 'Female'"),
):
    try:
        voices = await list_available_voices(language=language, gender=gender)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"success": True, "count": len(voices), "voices": voices}
