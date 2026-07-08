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
from pathlib import Path
from typing import Optional

from common.project_store import ProjectStoreError, save_visual_for_order
from tools.visual_creator.rasterize import RasterizeError, rasterize_svg_to_png_bytes
from tools.visual_creator.vlogshot.checklist import (
    ChecklistEntry,
    ChecklistParseError,
    parse_json_checklist,
)
from tools.visual_creator.vlogshot.cli import _process_entry, slugify
from tools.visual_creator.vlogshot.pathresolve import build_file_index
from tools.visual_creator.vlogshot.themes import DEFAULT_THEME, THEMES
from tools.visual_creator.vlogshot.render import DEFAULT_IMAGE_HEIGHT
from tools.visual_creator.vlogshot.zipextract import ZipExtractError, extract_zip
from common.files import sanitize_filename

OUTPUT_FORMATS = ("svg", "png", "both")


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


def _persist_rendered_entry(
    svg_scratch_path: str,
    call_prefix: str,
    persist_dir: str,
    output_format: str,
    detail: str,
) -> tuple[list[str], str]:
    """Move/rasterize one entry's rendered SVG into persist_dir.

    `svg_scratch_path` is the SVG that vlogshot's renderers just wrote into
    the scratch temp dir (they only ever produce SVG - that part is
    unchanged). Depending on `output_format`:
      - "svg": move the SVG into persist_dir as-is.
      - "png": read the SVG text and rasterize it straight to a >=4K PNG
        (no low-res intermediate), write only the PNG, discard the SVG.
      - "both": do both of the above.

    Returns (final_basenames, detail) - detail is passed through unchanged
    unless PNG rasterization fails, in which case it's extended with the
    rasterization error so it still shows up in the per-entry result.
    """
    base_svg_name = sanitize_filename(f"{call_prefix}_{os.path.basename(svg_scratch_path)}")
    base_stem = base_svg_name[:-4] if base_svg_name.endswith(".svg") else base_svg_name
    final_names: list[str] = []

    if output_format in ("png", "both"):
        with open(svg_scratch_path, "r", encoding="utf-8") as f:
            svg_text = f.read()
        try:
            png_bytes = rasterize_svg_to_png_bytes(svg_text)
        except RasterizeError as exc:
            detail = f"{detail} (PNG rasterization failed: {exc})"
        else:
            png_name = f"{base_stem}.png"
            with open(os.path.join(persist_dir, png_name), "wb") as f:
                f.write(png_bytes)
            final_names.append(png_name)

    if output_format in ("svg", "both"):
        shutil.move(svg_scratch_path, os.path.join(persist_dir, base_svg_name))
        if output_format == "both":
            final_names.insert(0, base_svg_name)
        else:
            final_names.append(base_svg_name)
    # else: PNG-only mode - the scratch SVG has served its purpose (source
    # for the rasterizer above) and is cleaned up with the rest of tmp_dir,
    # no need to move it into persist_dir.

    return final_names, detail


def generate_visuals_core(
    checklist: list[dict],
    zip_base64: Optional[str],
    persist_dir,
    theme: str = DEFAULT_THEME,
    style: str = "vscode",
    font_size: int = 22,
    image_width: int = 1920,
    image_height: int = DEFAULT_IMAGE_HEIGHT,
    output_format: str = "png",
    project_id: Optional[str] = None,
) -> dict:
    """Render every checklist entry to an SVG (and optionally a 4K PNG) and
    move the result(s) into persist_dir.

    Rendering happens in a scratch temp dir (mirroring vlogshot's own
    order:02d_slug.svg naming), then each produced file is copied into the
    shared, flat `persist_dir` (e.g. TEMP_DIR/visuals) under a call-unique
    name, the same way generated audio lands directly in TEMP_DIR - so a
    single GET /api/v1/visual/{filename} route can serve it, and repeat
    calls never collide or overwrite each other's output.

    Every code entry is rendered onto a fixed `image_width` x `image_height`
    canvas (default 1920x1080), regardless of how many lines it has, so a
    whole batch of screenshots is video-ready with no size mismatches
    between clips. Code always starts at the top of the canvas, right under
    the editor chrome, like a real editor; snippets too long to fit at the
    chosen font size are automatically split into multiple same-sized
    screenshots (pages), each still listed under that entry's "order" in
    `results`/`files`.

    `output_format`:
      - "svg" (default, unchanged behavior): only the SVG is produced.
      - "png": vlogshot's renderers still only know how to produce SVG, so
        the SVG is rendered first as always, then rasterized straight from
        that SVG source into a >=4K PNG (see app/core/rasterize.py) and only
        the PNG is kept in persist_dir.
      - "both": both the SVG and the 4K PNG are kept in persist_dir.

    `project_id`: if given, every entry's rendered file(s) are *also* copied
    into TEMP_DIR/projects/{project_id}/order_{NN}/visual.<ext> (or
    visual_p1.<ext>, visual_p2.<ext>, ... if paginated), and that order's
    meta.json / the project's manifest.json are updated - see
    app/core/project_store.py. This is what lets a later sync/render tool
    find "the visual for order N" without re-deriving it from the flat,
    hash-prefixed filenames in `files`. Each checklist entry's own "order"
    field is used, so this only works meaningfully when the checklist's
    orders line up with the matching voice_over calls' orders for the same
    project_id.

    Returns:
        {
          "results": [{"order", "label", "status", "detail"}, ...],
          "files": ["a1b2c3d4_01_foo.svg", "a1b2c3d4_01_foo_p2.svg", ...],
        }
    Raises VisualCreatorError for bad input (missing zip when needed,
    malformed checklist, invalid theme/style/output_format, corrupt zip).
    """
    if theme not in THEMES:
        raise VisualCreatorError(
            f"Invalid theme '{theme}'. Choose one of: {', '.join(sorted(THEMES))}"
        )
    if style not in ("vscode", "minimal"):
        raise VisualCreatorError(f"Invalid style '{style}'. Choose 'vscode' or 'minimal'.")
    if output_format not in OUTPUT_FORMATS:
        raise VisualCreatorError(
            f"Invalid output_format '{output_format}'. Choose one of: "
            f"{', '.join(OUTPUT_FORMATS)}"
        )

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
            status, detail, produced_paths = _process_entry(
                entry, project_root, file_index, scratch_out, theme,
                font_size, style, image_width, image_height,
            )

            if produced_paths:
                entry_files = []
                for produced_path in produced_paths:
                    page_files, detail = _persist_rendered_entry(
                        produced_path, call_prefix, persist_dir, output_format, detail
                    )
                    entry_files.extend(page_files)
                files.extend(entry_files)
                if not entry_files:
                    # SVG(s) rendered fine, but PNG-only rasterization failed
                    # for all of them: nothing usable was produced for this
                    # entry after all.
                    status = "SKIPPED"
                elif project_id:
                    try:
                        save_visual_for_order(
                            project_id=project_id,
                            order=entry.order,
                            src_visual_paths=[
                                Path(persist_dir) / name for name in entry_files
                            ],
                            label=entry.label,
                            width=image_width,
                            height=image_height,
                        )
                    except ProjectStoreError as exc:
                        detail = f"{detail} (project sync save failed: {exc})".strip()

            results.append(
                {"order": entry.order, "label": entry.label, "status": status, "detail": detail}
            )

        return {"results": results, "files": files}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
