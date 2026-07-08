"""
Project-based storage for syncable audio + visual pairs.

Problem this solves
--------------------
`voice_over` and `visual_creator` each write to their own flat temp folder
under unrelated, hash-based filenames (see app/core/files.py). Nothing ties
a generated audio file to the screenshot it should play under, even though
the skill that drives both already knows this pairing via a shared "order"
number:

    {"visuals": [{"order": 1, "label": "...", ...}, ...],
     "script":  [{"order": 1, "label": "...", "script": "..."}, ...]}

This module gives both tools a second, optional place to also write their
output: a per-project, per-order folder, plus one manifest.json per project
that a future sync/render tool can read in a single call to get everything
it needs (paths, durations, labels, script text) without guessing.

Layout on disk
---------------
    TEMP_DIR/projects/{project_id}/
        manifest.json
        order_01/
            audio.mp3
            visual.png            (or visual.svg, or visual_p1.png + visual_p2.png
                                     if the code screenshot was paginated)
            meta.json
        order_02/
            ...

`meta.json` per order holds everything gathered so far for that beat:
    {
      "order": 1,
      "label": "zip slip protection check",
      "script_text": "Now here's the interesting part...",
      "audio": {"filename": "audio.mp3", "duration_seconds": 8.4, ...},
      "visual": {"filenames": ["visual.png"], "width": 3840, "height": 2160}
    }

`manifest.json` at the project root is the same information flattened into
one ordered list - the single file a sync tool needs to read:
    {
      "project_id": "my-vlog",
      "updated_at": "...",
      "orders": [ {...order_01 meta...}, {...order_02 meta...}, ... ]
    }

Nothing here renders video - it only manages where files land and keeps
the manifest that describes how they relate, so that a later sync/render
step is a simple read instead of a filename treasure hunt.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Optional

from common.config import PROJECTS_DIR
from common.formatting import utc_now_iso

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")


class ProjectStoreError(ValueError):
    """Raised for invalid project_id/order or on-disk inconsistencies."""


def sanitize_project_id(project_id: str) -> str:
    """Constrain project_id to safe path characters (no traversal, no slashes)."""
    if not project_id or not project_id.strip():
        raise ProjectStoreError("'project_id' cannot be empty.")
    cleaned = _SAFE_ID_RE.sub("_", project_id.strip()).strip("._")
    if not cleaned:
        raise ProjectStoreError(f"'project_id' has no valid characters: {project_id!r}")
    return cleaned[:120]


def _order_dirname(order: int) -> str:
    if order < 0:
        raise ProjectStoreError(f"'order' must be >= 0, got {order}.")
    return f"order_{order:02d}"


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / sanitize_project_id(project_id)


def order_dir(project_id: str, order: int, create: bool = False) -> Path:
    path = project_dir(project_id) / _order_dirname(order)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def manifest_path(project_id: str) -> Path:
    return project_dir(project_id) / "manifest.json"


# ---------------------------------------------------------------------------
# Per-order metadata
# ---------------------------------------------------------------------------

def _read_order_meta(project_id: str, order: int) -> dict:
    meta_file = order_dir(project_id, order) / "meta.json"
    if not meta_file.exists():
        return {"order": order, "label": None, "script_text": None, "audio": None, "visual": None}
    with open(meta_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_order_meta(project_id: str, order: int, meta: dict) -> None:
    out_dir = order_dir(project_id, order, create=True)
    with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def save_audio_for_order(
    project_id: str,
    order: int,
    src_audio_path: Path,
    label: Optional[str] = None,
    script_text: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> dict:
    """Copy a generated audio file into projects/{id}/order_{NN}/audio.mp3
    and record it (plus optional label/script/duration) in that order's
    meta.json. Safe to call before or after save_visual_for_order for the
    same order - each only touches its own key in meta.json.

    Returns the updated meta dict for this order.
    """
    out_dir = order_dir(project_id, order, create=True)
    dest = out_dir / f"audio{src_audio_path.suffix or '.mp3'}"
    shutil.copyfile(src_audio_path, dest)

    meta = _read_order_meta(project_id, order)
    meta["order"] = order
    if label is not None:
        meta["label"] = label
    if script_text is not None:
        meta["script_text"] = script_text
    meta["audio"] = {
        "filename": dest.name,
        "duration_seconds": duration_seconds,
    }
    _write_order_meta(project_id, order, meta)
    _rebuild_manifest(project_id)
    return meta


def save_visual_for_order(
    project_id: str,
    order: int,
    src_visual_paths: list[Path],
    label: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> dict:
    """Copy one or more generated visual files (a code screenshot, or
    multiple pages of one if it was paginated) into
    projects/{id}/order_{NN}/ and record them in that order's meta.json.

    Filenames are normalized to visual.<ext> for a single file, or
    visual_p1.<ext>, visual_p2.<ext>, ... for multiple pages, so a sync
    tool can find them without parsing the original vlogshot filenames.

    Returns the updated meta dict for this order.
    """
    if not src_visual_paths:
        raise ProjectStoreError("save_visual_for_order requires at least one source path.")

    out_dir = order_dir(project_id, order, create=True)
    dest_names = []
    multi = len(src_visual_paths) > 1
    for idx, src in enumerate(src_visual_paths, start=1):
        suffix = src.suffix or ".png"
        dest_name = f"visual_p{idx}{suffix}" if multi else f"visual{suffix}"
        shutil.copyfile(src, out_dir / dest_name)
        dest_names.append(dest_name)

    meta = _read_order_meta(project_id, order)
    meta["order"] = order
    if label is not None:
        meta["label"] = label
    meta["visual"] = {
        "filenames": dest_names,
        "width": width,
        "height": height,
    }
    _write_order_meta(project_id, order, meta)
    _rebuild_manifest(project_id)
    return meta


# ---------------------------------------------------------------------------
# Manifest (project-wide index)
# ---------------------------------------------------------------------------

def _rebuild_manifest(project_id: str) -> dict:
    """Recompute manifest.json from every order_*/meta.json on disk.

    Rebuilding from disk (rather than incrementally patching the manifest)
    means the manifest can never drift from the per-order meta files, even
    if audio and visuals for the same order are saved in separate calls,
    possibly minutes apart or across process restarts.
    """
    p_dir = project_dir(project_id)
    p_dir.mkdir(parents=True, exist_ok=True)

    orders = []
    for order_path in sorted(p_dir.glob("order_*")):
        meta_file = order_path / "meta.json"
        if not meta_file.exists():
            continue
        with open(meta_file, "r", encoding="utf-8") as f:
            orders.append(json.load(f))
    orders.sort(key=lambda m: m.get("order", 0))

    manifest = {
        "project_id": project_id,
        "updated_at": utc_now_iso(),
        "orders": orders,
    }
    with open(manifest_path(project_id), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def get_manifest(project_id: str) -> dict:
    """Read (or build, if missing) the manifest for a project."""
    m_path = manifest_path(project_id)
    if not m_path.exists():
        return _rebuild_manifest(project_id)
    with open(m_path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_projects() -> list[str]:
    """List known project_ids (i.e. subfolders of PROJECTS_DIR)."""
    if not PROJECTS_DIR.exists():
        return []
    return sorted(p.name for p in PROJECTS_DIR.iterdir() if p.is_dir())


def resolve_project_file(project_id: str, order: int, filename: str) -> Path:
    """Resolve a filename inside one order's folder, guarding against
    path traversal by only ever using the basename."""
    safe_name = Path(filename).name
    return order_dir(project_id, order) / safe_name


# ---------------------------------------------------------------------------
# Final rendered video (video_renderer)
# ---------------------------------------------------------------------------

FINAL_VIDEO_FILENAME = "final_output.mp4"


def final_video_path(project_id: str) -> Path:
    """Path to a project's rendered video, whether or not it exists yet."""
    return project_dir(project_id) / FINAL_VIDEO_FILENAME


def save_final_video(project_id: str, src_path: Path) -> Path:
    """Copy a rendered MP4 into projects/{project_id}/final_output.mp4.

    Unlike save_audio_for_order/save_visual_for_order, this isn't tied to
    one order - it's the single, whole-project output a render tool
    produces once it has stitched every order's segment together - so it
    lives at the project root next to manifest.json rather than inside an
    order_{NN}/ folder.

    Returns the destination path. Raises ProjectStoreError if src_path
    doesn't exist.
    """
    if not src_path.exists():
        raise ProjectStoreError(f"Source video does not exist: {src_path}")

    p_dir = project_dir(project_id)
    p_dir.mkdir(parents=True, exist_ok=True)
    dest = final_video_path(project_id)
    shutil.copyfile(src_path, dest)
    return dest


def cleanup_expired_projects(ttl_seconds: int) -> int:
    """Delete whole project folders whose manifest hasn't been touched in
    ttl_seconds. Returns the count of projects removed."""
    removed = 0
    now = time.time()
    if not PROJECTS_DIR.exists():
        return 0
    for p_dir in PROJECTS_DIR.iterdir():
        if not p_dir.is_dir():
            continue
        m_path = p_dir / "manifest.json"
        check_path = m_path if m_path.exists() else p_dir
        try:
            if now - check_path.stat().st_mtime > ttl_seconds:
                shutil.rmtree(p_dir, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
