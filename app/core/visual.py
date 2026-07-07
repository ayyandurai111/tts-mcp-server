"""Core logic for the `visual_creator` tool.

Thin orchestration layer around the vendored `vlogshot` package
(app/core/vlogshot/) - turns a checklist of code/command entries (plus an
optional project zip) into a set of SVG screenshots on disk, the same way
`vlogshot.cli.main()` does for the standalone CLI tool. This module is the
programmatic equivalent: it takes already-parsed-JSON entries and raw zip
bytes instead of argv/file paths, and never touches sys.argv or calls
sys.exit - it just returns a result dict, so it's safe to call from an
async MCP handler.
"""

from __future__ import annotations

import base64
import binascii
import os
import shutil
import tempfile
import uuid
from typing import Optional

from app.core.vlogshot.checklist import (
    ChecklistEntry,
    ChecklistParseError,
    parse_json_checklist,
)
from app.core.vlogshot.cli import _process_entry, slugify
from app.core.vlogshot.pathresolve import build_file_index
from app.core.vlogshot.themes import DEFAULT_THEME, THEMES
from app.core.vlogshot.zipextract import ZipExtractError, extract_zip
from app.core.files import sanitize_filename


class VisualCreatorError(ValueError):
    """Raised for input problems that should be reported back, not raised as 500s."""


def _entries_from_dicts(raw_entries: list[dict]) -> list[ChecklistEntry]:
    """Reuse vlogshot's own JSON-checklist parser/validation.

    The MCP tool already hands us a parsed JSON array (from the tool-call
    arguments), so we round-trip it through json.dumps rather than
    duplicating parse_json_checklist's validation logic here.
    """
    import json

    if not isinstance(raw_entries, list) or not raw_entries:
        raise VisualCreatorError("'checklist' must be a non-empty array of entries.")

    try:
        text = json.dumps(raw_entries)
    except (TypeError, ValueError) as exc:
        raise VisualCreatorError(f"'checklist' is not JSON-serializable: {exc}") from exc

    try:
        return parse_json_checklist(text, source_name="checklist")
    except ChecklistParseError as exc:
        raise VisualCreatorError(str(exc)) from exc


def generate_visuals_core(
    checklist: list[dict],
    zip_base64: Optional[str],
    persist_dir,
    theme: str = DEFAULT_THEME,
    style: str = "vscode",
    font_size: int = 22,
    image_width: int = 1920,
) -> dict:
    """Render every checklist entry to an SVG and move it into persist_dir.

    Rendering happens in a scratch temp dir (mirroring vlogshot's own
    order:02d_slug.svg naming), then each produced file is copied into the
    shared, flat `persist_dir` (e.g. TEMP_DIR/visuals) under a call-unique
    name, the same way generated audio lands directly in TEMP_DIR - so a
    single GET /api/v1/visual/{filename} route can serve it, and repeat
    calls never collide or overwrite each other's output.

    Returns:
        {
          "results": [{"order", "label", "status", "detail"}, ...],
          "files": ["a1b2c3d4_01_foo.svg", ...],   # final basenames, in order
        }
    Raises VisualCreatorError for bad input (missing zip when needed,
    malformed checklist, invalid theme/style, corrupt zip).
    """
    if theme not in THEMES:
        raise VisualCreatorError(
            f"Invalid theme '{theme}'. Choose one of: {', '.join(sorted(THEMES))}"
        )
    if style not in ("vscode", "minimal"):
        raise VisualCreatorError(f"Invalid style '{style}'. Choose 'vscode' or 'minimal'.")

    entries = _entries_from_dicts(checklist)

    needs_zip = any(e.kind == "code" for e in entries)
    if needs_zip and not zip_base64:
        raise VisualCreatorError(
            "'zip_base64' is required because the checklist has at least one "
            "zip-lookup code entry (file/start_line/end_line without an inline "
            "'code' field). Add zip_base64, or give that entry a 'code' field "
            "to skip the zip lookup."
        )

    persist_dir = str(persist_dir)
    os.makedirs(persist_dir, exist_ok=True)

    tmp_dir = tempfile.mkdtemp(prefix="visual_creator_")
    try:
        project_root = None
        file_index = None

        if needs_zip:
            try:
                zip_bytes = base64.b64decode(zip_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise VisualCreatorError(f"'zip_base64' is not valid base64: {exc}") from exc

            zip_path = os.path.join(tmp_dir, "project.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_bytes)

            try:
                project_root = extract_zip(zip_path, os.path.join(tmp_dir, "project"))
            except ZipExtractError as exc:
                raise VisualCreatorError(str(exc)) from exc
            file_index = build_file_index(project_root)

        scratch_out = os.path.join(tmp_dir, "out")
        os.makedirs(scratch_out, exist_ok=True)

        # One short prefix per call keeps every file from this run grouped
        # and guarantees no clash with any other call's output in the same
        # shared, flat persist_dir.
        call_prefix = uuid.uuid4().hex[:8]

        results = []
        files = []
        for entry in entries:
            status, detail, produced_path = _process_entry(
                entry, project_root, file_index, scratch_out, theme,
                font_size, style, image_width,
            )
            results.append(
                {"order": entry.order, "label": entry.label, "status": status, "detail": detail}
            )
            if produced_path:
                final_name = sanitize_filename(f"{call_prefix}_{os.path.basename(produced_path)}")
                shutil.move(produced_path, os.path.join(persist_dir, final_name))
                files.append(final_name)

        return {"results": results, "files": files}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
