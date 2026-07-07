"""
Command-line entry point.

Usage:
    python generate_screenshots.py --zip project.zip --checklist checklist.json --out output/
    python generate_screenshots.py --zip project.zip --checklist checklist.txt --out output/
    python generate_screenshots.py --zip project.zip --script vlog_script.md --out output/
    python generate_screenshots.py --checklist checklist.json --out output/   # no zip needed if
                                                                                # every entry is
                                                                                # inline code / a command

Checklists can mix three kinds of entries:
  - code screenshots (file + line range, looked up in --zip) -> editor window
  - inline code screenshots (path/filename + line range + the code text
    itself, given directly in JSON — no --zip needed) -> editor window
  - command screenshots (a command + its captured output) -> terminal window

--zip is only required if at least one entry is a zip-lookup code entry.

See README.md for the exact syntax for each checklist format.
"""

import argparse
import os
import re
import sys
import tempfile
import shutil

from .checklist import (
    ChecklistParseError,
    load_checklist,
    extract_from_script,
)
from .zipextract import extract_zip, ZipExtractError
from .pathresolve import build_file_index, resolve_file
from .render import render_code_screenshot
from .render_terminal import render_terminal_screenshot
from .themes import THEMES, DEFAULT_THEME


def slugify(text, max_len=60):
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = "snippet"
    return text[:max_len].rstrip("_") or "snippet"


def build_arg_parser():
    p = argparse.ArgumentParser(
        prog="generate_screenshots.py",
        description="Generate clean, syntax-highlighted code screenshots from a project "
        "zip and a capture checklist — for coding vlogs.",
    )
    p.add_argument(
        "--zip",
        dest="zip_path",
        default=None,
        help="Path to the project zip file. Only required if the checklist "
        "contains at least one zip-lookup code entry (plain file/line-range "
        "entries); not needed if every entry is inline code or a command.",
    )

    checklist_group = p.add_mutually_exclusive_group(required=True)
    checklist_group.add_argument(
        "--checklist",
        dest="checklist_path",
        help="Path to a checklist file (.json or plain-text format, auto-detected).",
    )
    checklist_group.add_argument(
        "--script",
        dest="script_path",
        help="Path to a raw vlog script markdown file containing "
        "'[Screenshot] path, lines N-M' markers to auto-extract.",
    )

    p.add_argument("--out", default="output", dest="out_dir", help="Output directory for SVG screenshots (default: output/).")
    p.add_argument(
        "--theme",
        default=DEFAULT_THEME,
        choices=sorted(THEMES.keys()),
        help=f"Color theme (default: {DEFAULT_THEME}).",
    )
    p.add_argument(
        "--font-size",
        type=int,
        default=22,
        dest="font_size",
        help="Font size in pixels (default: 22).",
    )
    p.add_argument(
        "--style",
        default="vscode",
        choices=["vscode", "minimal"],
        help="'vscode' for a full editor window (tabs, breadcrumbs, minimap, "
        "status bar) or 'minimal' for just a header bar (default: vscode).",
    )
    p.add_argument(
        "--width",
        type=int,
        default=1920,
        dest="image_width",
        help="Output image width in pixels (default: 1920, HD).",
    )
    return p


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # --- Load checklist (fail early, clearly) --------------------------------
    try:
        if args.checklist_path:
            entries = load_checklist(args.checklist_path)
        else:
            with open(args.script_path, "r", encoding="utf-8") as f:
                script_text = f.read()
            entries = extract_from_script(script_text, source_name=args.script_path)
    except FileNotFoundError as e:
        print(f"ERROR: checklist/script file not found: {e.filename}", file=sys.stderr)
        return 1
    except ChecklistParseError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # --- Extract zip only if some entry actually needs it (fail early, clearly) --
    needs_zip = any(e.kind == "code" for e in entries)
    if needs_zip and not args.zip_path:
        print(
            "ERROR: --zip is required because the checklist has at least one "
            "zip-lookup code entry (file/start_line/end_line without inline 'code'). "
            "Add --zip, or give that entry a 'code' field to skip the zip lookup.",
            file=sys.stderr,
        )
        return 1

    tmp_dir = tempfile.mkdtemp(prefix="vlogshot_") if needs_zip else None
    try:
        project_root = None
        file_index = None
        if needs_zip:
            try:
                project_root = extract_zip(args.zip_path, os.path.join(tmp_dir, "project"))
            except ZipExtractError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 1
            file_index = build_file_index(project_root)

        os.makedirs(args.out_dir, exist_ok=True)

        results = []  # (order, label, status, detail, out_path_or_None)
        generated_files = []

        for entry in entries:
            status, detail, out_path = _process_entry(
                entry, project_root, file_index, args.out_dir, args.theme,
                args.font_size, args.style, args.image_width,
            )
            results.append((entry.order, entry.label, status, detail))
            if out_path:
                generated_files.append((entry.order, out_path))

        _print_summary(results, generated_files)

        # Non-zero exit if everything failed (helps scripting/CI use),
        # but zero exit if at least one screenshot was produced.
        return 0 if generated_files else 1
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _process_entry(entry, project_root, file_index, out_dir, theme, font_size,
                    style, image_width):
    """
    Process a single checklist entry end-to-end.
    Returns (status, detail, out_path_or_None) where status is one of
    'OK', 'CLIPPED', 'SKIPPED'.
    """
    if entry.kind == "command":
        return _process_command_entry(entry, out_dir)
    if entry.kind == "inline_code":
        return _process_inline_code_entry(entry, out_dir, theme, font_size, style, image_width)
    return _process_code_entry(entry, project_root, file_index, out_dir, theme,
                                font_size, style, image_width)


def _process_command_entry(entry, out_dir):
    slug = slugify(entry.label)
    filename = f"{entry.order:02d}_{slug}.svg"
    out_path = os.path.join(out_dir, filename)

    try:
        render_terminal_screenshot(entry.command, entry.output or "", out_path)
    except Exception as e:  # noqa: BLE001 - want to keep processing other entries
        return "SKIPPED", f"rendering failed: {e}", None

    return "OK", "", out_path


def _process_inline_code_entry(entry, out_dir, theme, font_size, style, image_width):
    # The code is given directly — no zip, no file lookup, no line-range
    # slicing against a real file. start_line just sets the gutter numbers.
    display_path = entry.file
    if entry.filename:
        parts = display_path.replace("\\", "/").split("/")
        parts[-1] = entry.filename
        display_path = "/".join(parts)

    code_text = entry.code
    if code_text and not code_text.endswith("\n"):
        code_text += "\n"

    slug = slugify(entry.label)
    filename = f"{entry.order:02d}_{slug}.svg"
    out_path = os.path.join(out_dir, filename)

    try:
        render_code_screenshot(
            code_text,
            file_path=display_path,
            start_line=entry.start_line or 1,
            out_path=out_path,
            theme_name=theme,
            font_size=font_size,
            style=style,
            image_width=image_width,
        )
    except Exception as e:  # noqa: BLE001 - want to keep processing other entries
        return "SKIPPED", f"rendering failed: {e}", None

    return "OK", "", out_path


def _process_code_entry(entry, project_root, file_index, out_dir, theme, font_size,
                         style, image_width):
    # Empty / inverted range
    if entry.start_line > entry.end_line:
        return "SKIPPED", "empty line range (start_line > end_line)", None

    # Resolve the file path leniently.
    result = resolve_file(project_root, entry.file, file_index)
    if result.path is None:
        return "SKIPPED", f"file not found: '{entry.file}'", None

    ambiguity_note = ""
    if result.ambiguous_candidates:
        others = ", ".join(result.ambiguous_candidates[:3])
        ambiguity_note = f" (ambiguous match — also found: {others}; chose '{result.path}')"

    full_path = os.path.join(project_root, result.path)
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except OSError as e:
        return "SKIPPED", f"could not read '{result.path}': {e}", None

    total_lines = len(all_lines)
    status = "OK"
    detail = ambiguity_note.strip()

    start = entry.start_line
    end = entry.end_line

    if start > total_lines:
        return "SKIPPED", (
            f"start_line {start} is beyond end of file ({total_lines} lines)" + ambiguity_note
        ), None

    if end > total_lines:
        end = total_lines
        status = "CLIPPED"
        clip_note = f"clipped end_line {entry.end_line} -> {total_lines} (end of file)"
        detail = (clip_note + ambiguity_note).strip()

    code_lines = all_lines[start - 1:end]
    code_text = "".join(code_lines)
    if code_text and not code_text.endswith("\n"):
        code_text += "\n"

    slug = slugify(entry.label)
    filename = f"{entry.order:02d}_{slug}.svg"
    out_path = os.path.join(out_dir, filename)

    try:
        render_code_screenshot(
            code_text,
            file_path=result.path,
            start_line=start,
            out_path=out_path,
            theme_name=theme,
            font_size=font_size,
            style=style,
            image_width=image_width,
        )
    except Exception as e:  # noqa: BLE001 - want to keep processing other entries
        return "SKIPPED", f"rendering failed: {e}" + ambiguity_note, None

    return status, detail, out_path


def _print_summary(results, generated_files):
    print()
    print("=" * 60)
    print("Vlog Code-Screenshot Generator — Summary")
    print("=" * 60)

    for order, label, status, detail in results:
        line = f"[{order:02d}] {status:8s} {label}"
        if detail:
            line += f" — {detail}"
        print(line)

    print()
    if generated_files:
        print(f"Generated {len(generated_files)} screenshot(s), in order:")
        for order, path in sorted(generated_files, key=lambda t: t[0]):
            print(f"  {path}")
    else:
        print("No screenshots were generated.")

    warnings = [(o, l, s, d) for (o, l, s, d) in results if s != "OK"]
    if warnings:
        print()
        print(f"{len(warnings)} entr{'y' if len(warnings) == 1 else 'ies'} needed attention:")
        for order, label, status, detail in warnings:
            print(f"  [{order:02d}] {status}: {label}" + (f" — {detail}" if detail else ""))
    print()


if __name__ == "__main__":
    sys.exit(main())
