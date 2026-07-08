"""GET /api/v1/project/{project_id} - read a project's sync manifest.

GET /api/v1/project/{project_id}/{order}/{filename} - download one file
(audio.mp3, visual.png, etc.) from a specific order folder within a
project. Complements /api/v1/audio/{filename} and /api/v1/visual/{filename}
(which serve the flat, hash-prefixed copies) by serving the project-grouped
copies directly, which is what a sync/render tool actually wants to walk.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from common.project_store import (
    ProjectStoreError,
    final_video_path,
    get_manifest,
    list_projects,
    project_dir,
    resolve_project_file,
)

router = APIRouter(prefix="/api/v1", tags=["projects"])

_MEDIA_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".mp3": "audio/mpeg",
    ".json": "application/json",
}
_DEFAULT_MEDIA_TYPE = "application/octet-stream"


@router.get("/projects")
async def get_projects():
    """List known project_ids currently on disk."""
    return {"projects": list_projects()}


@router.get("/project/{project_id}")
async def get_project_manifest(project_id: str):
    """Return the sync manifest for one project: every order's label,
    script text, audio duration, and visual filename(s) - everything a
    sync/render tool needs in one call."""
    try:
        if not project_dir(project_id).exists():
            raise HTTPException(status_code=404, detail=f"Unknown project_id '{project_id}'.")
        return get_manifest(project_id)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_id}/video")
async def get_project_video(project_id: str):
    """Stream back a project's rendered final_output.mp4 (produced by the
    video_renderer MCP tool). Declared ahead of the generic
    /{order}/{filename} route below so FastAPI's routing (which tries
    routes in declaration order) doesn't attempt to match "video" against
    that route's int-typed {order} path param first."""
    try:
        file_path = final_video_path(project_id)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No rendered video found for project '{project_id}'. Run "
                "the video_renderer tool first, or the server may have "
                "restarted (temp storage is ephemeral)."
            ),
        )
    return FileResponse(path=file_path, media_type="video/mp4", filename=file_path.name)


@router.get("/project/{project_id}/{order}/{filename}")
async def get_project_file(project_id: str, order: int, filename: str):
    """Stream back one file (audio.mp3, visual.png, ...) from a project's
    order_{NN}/ folder."""
    try:
        file_path = resolve_project_file(project_id, order, filename)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"'{filename}' not found for project '{project_id}' order {order}. "
                "It may have expired or the server may have restarted "
                "(temp storage is ephemeral)."
            ),
        )
    media_type = _MEDIA_TYPES.get(file_path.suffix.lower(), _DEFAULT_MEDIA_TYPE)
    return FileResponse(path=file_path, media_type=media_type, filename=file_path.name)
