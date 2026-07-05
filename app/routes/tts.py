"""POST /api/v1/tts - generate speech via plain REST (mirrors the MCP tool)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.files import generate_filename, resolve_temp_path
from app.core.tts import TTSGenerationError, generate_audio_core
from app.models.schemas import AudioInfo, TTSRequest, TTSResponse
from app.utils.formatting import utc_now_iso

router = APIRouter(prefix="/api/v1", tags=["tts"])


@router.post("/tts", response_model=TTSResponse)
async def rest_tts(body: TTSRequest):
    """Generate speech from text. Any client (AI or otherwise) can call this."""
    filename = generate_filename(body.text, body.voice, body.output_filename)
    output_path = resolve_temp_path(filename)

    try:
        audio_info = await generate_audio_core(
            text=body.text,
            output_path=output_path,
            voice=body.voice,
            rate=body.rate,
            pitch=body.pitch,
            volume=body.volume,
        )
    except TTSGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return TTSResponse(
        success=True,
        content=body.text[:500] + ("..." if len(body.text) > 500 else ""),
        audio=AudioInfo(
            filename=audio_info["file_name"],
            file_size_bytes=audio_info["file_size_bytes"],
            file_size_human=audio_info["file_size_human"],
            url=f"/api/v1/audio/{audio_info['file_name']}",
        ),
        voice={
            "id": body.voice,
            "rate": body.rate,
            "pitch": body.pitch,
            "volume": body.volume,
        },
        timestamp=utc_now_iso(),
    )
