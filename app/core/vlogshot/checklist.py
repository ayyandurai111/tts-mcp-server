"""
Parsing for the three supported checklist input shapes:

1. JSON  — a list of entries, each one of:
     - a code entry (looked up in the project zip):
           {order, file, start_line, end_line, label}
     - an inline code entry (no zip needed — the source is given directly):
           {order, path, start_line, end_line, code, filename, label}
     - a command entry:
           {order, type: "command", command, output, label}
2. Plain text — one entry per line: "path/to/file.py:12-30:label text"
   (inline code / command entries are not supported in this format — use JSON)
3. Vlog script markdown — lines matching "[Screenshot] path/to/file.py, lines N-M"
   (the label is taken from the rest of that line / a following description,
   see `extract_from_script` for the exact heuristic).

All three converge on the same internal representation: a list of
`ChecklistEntry` namedtuples, already sorted by `order`.
  - kind="code": `file`/`start_line`/`end_line` set; resolved from the
    project zip at render time.
  - kind="inline_code": `file`/`start_line` set, `code` holds the actual
    source text to render directly (no zip lookup at all); `filename`,
    if given, overrides the tab/title display name.
  - kind="command": `command`/`output` set; `file`/`start_line`/`end_line`
    are None.
"""

import json
import re
from collections import namedtuple

ChecklistEntry = namedtuple(
    "ChecklistEntry",
    ["order", "file", "start_line", "end_line", "label", "kind", "command", "output",
     "code", "filename"],
)
ChecklistEntry.__new__.__defaults__ = ("code", None, None, None, None)


class ChecklistParseError(ValueError):
    """Raised when a checklist file is malformed. Carries a precise message."""


_COMMAND_TYPE_ALIASES = {"command", "cmd", "terminal"}


# ---------------------------------------------------------------------------
# JSON format
# ---------------------------------------------------------------------------

def parse_json_checklist(text, source_name="checklist"):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ChecklistParseError(
            f"{source_name}: invalid JSON — {e.msg} (line {e.lineno}, column {e.colno})"
        ) from e

    if not isinstance(data, list):
        raise ChecklistParseError(
            f"{source_name}: expected a JSON list of entries at the top level, "
            f"got {type(data).__name__}"
        )

    entries = []
    for i, item in enumerate(data):
        ctx = f"{source_name}: entry #{i + 1}"
        if not isinstance(item, dict):
            raise ChecklistParseError(f"{ctx}: expected an object, got {type(item).__name__}")

        order = item.get("order", i + 1)
        try:
            order = int(order)
        except (TypeError, ValueError):
            raise ChecklistParseError(f"{ctx}: 'order' must be an integer")

        item_type = str(item.get("type", "code")).strip().lower()

        if item_type in _COMMAND_TYPE_ALIASES:
            command = item.get("command")
            if not command or not str(command).strip():
                raise ChecklistParseError(f"{ctx}: command entries require a non-empty 'command'")
            command = str(command)
            output = str(item.get("output", ""))
            label = str(item.get("label") or _default_command_label(command))
            entries.append(
                ChecklistEntry(order, None, None, None, label, "command", command, output)
            )
            continue

        if "code" in item:
            code_text = item.get("code")
            if not isinstance(code_text, str) or not code_text.strip():
                raise ChecklistParseError(f"{ctx}: 'code' must be a non-empty string")

            file_path = str(item.get("path") or item.get("file") or "").strip()
            if not file_path:
                raise ChecklistParseError(
                    f"{ctx}: inline code entries require a non-empty 'path' (or 'file')"
                )

            try:
                start_line = int(item.get("start_line", 1))
            except (TypeError, ValueError):
                raise ChecklistParseError(f"{ctx}: 'start_line' must be an integer")

            end_line = item.get("end_line")
            if end_line is not None:
                try:
                    end_line = int(end_line)
                except (TypeError, ValueError):
                    raise ChecklistParseError(f"{ctx}: 'end_line' must be an integer")

            filename_override = item.get("filename")
            if filename_override is not None:
                filename_override = str(filename_override).strip() or None

            label = str(
                item.get("label")
                or _default_label(file_path, start_line, end_line or start_line)
            )

            entries.append(
                ChecklistEntry(
                    order, file_path, start_line, end_line, label, "inline_code",
                    None, None, code_text, filename_override,
                )
            )
            continue

        missing = [k for k in ("file", "start_line", "end_line") if k not in item]
        if missing:
            raise ChecklistParseError(f"{ctx}: missing required field(s): {', '.join(missing)}")

        try:
            start_line = int(item["start_line"])
            end_line = int(item["end_line"])
        except (TypeError, ValueError):
            raise ChecklistParseError(
                f"{ctx}: 'start_line' and 'end_line' must be integers"
            )

        file_path = str(item["file"]).strip()
        if not file_path:
            raise ChecklistParseError(f"{ctx}: 'file' must not be empty")

        label = str(item.get("label") or _default_label(file_path, start_line, end_line))

        entries.append(ChecklistEntry(order, file_path, start_line, end_line, label))

    entries.sort(key=lambda e: e.order)
    return entries


# ---------------------------------------------------------------------------
# Plain text format:  path/to/file.py:12-30:label text
# Also supports a command entry:
#   CMD: pip install requests
#   > Collecting requests
#   > Successfully installed requests-2.31.0
# (the "> "-prefixed lines immediately following a CMD: line are its
# captured output; a blank line or EOF ends the output block)
# ---------------------------------------------------------------------------

_TEXT_LINE_RE = re.compile(
    r"""^\s*
        (?P<file>[^:]+)
        :
        (?P<start>\d+)\s*-\s*(?P<end>\d+)
        (?: : (?P<label>.*) )?
        \s*$""",
    re.VERBOSE,
)

_CMD_LINE_RE = re.compile(r"^\s*CMD:\s*(?P<command>.+?)\s*$", re.IGNORECASE)
_OUTPUT_LINE_RE = re.compile(r"^>\s?(?P<text>.*)$")


def parse_text_checklist(text, source_name="checklist"):
    entries = []
    order = 0
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.strip()
        lineno = i + 1
        i += 1

        if not line or line.startswith("#"):
            continue

        cmd_m = _CMD_LINE_RE.match(line)
        if cmd_m:
            command = cmd_m.group("command")
            output_lines = []
            while i < len(lines):
                out_m = _OUTPUT_LINE_RE.match(lines[i])
                if not out_m:
                    break
                output_lines.append(out_m.group("text"))
                i += 1
            order += 1
            entries.append(
                ChecklistEntry(
                    order, None, None, None, _default_command_label(command),
                    "command", command, "\n".join(output_lines),
                )
            )
            continue

        m = _TEXT_LINE_RE.match(line)
        if not m:
            raise ChecklistParseError(
                f"{source_name}: line {lineno} doesn't match the expected "
                f"'path/to/file.ext:START-END:label' or 'CMD: ...' format: {raw_line!r}"
            )

        file_path = m.group("file").strip()
        start_line = int(m.group("start"))
        end_line = int(m.group("end"))
        label = (m.group("label") or "").strip() or _default_label(file_path, start_line, end_line)

        order += 1
        entries.append(ChecklistEntry(order, file_path, start_line, end_line, label))

    if not entries:
        raise ChecklistParseError(f"{source_name}: no valid entries found")

    return entries


# ---------------------------------------------------------------------------
# Vlog script markdown format:
#   [Screenshot] app/core/tts.py, lines 12-30
#   optionally followed by a short description line used as the label
#
#   [Terminal] pip install requests
#   > Collecting requests
#   > Successfully installed requests-2.31.0
#   (a command screenshot: any immediately-following "> "-prefixed lines
#   are captured as its output, same as the CMD: syntax in plain text)
# ---------------------------------------------------------------------------

_SCRIPT_LINE_RE = re.compile(
    r"""\[Screenshot\]\s*
        (?P<file>\S+?)
        \s*,\s*
        lines?\s+(?P<start>\d+)\s*-\s*(?P<end>\d+)
        (?:\s*[:\-]\s*(?P<inline_label>.+))?
        \s*$""",
    re.VERBOSE | re.IGNORECASE,
)

_SCRIPT_TERMINAL_RE = re.compile(
    r"""\[Terminal\]\s*(?P<command>.+?)\s*$""",
    re.VERBOSE | re.IGNORECASE,
)


def extract_from_script(text, source_name="script"):
    """
    Scan a raw vlog script markdown file for lines like:
        [Screenshot] app/core/tts.py, lines 12-30
        [Screenshot] app/core/tts.py, lines 12-30: generate_audio_core function
        [Terminal] pip install requests

    If no inline label is present on the same line, look at the next
    non-empty line for a short description to use as the label.
    """
    lines = text.splitlines()
    entries = []
    order = 0
    i = 0

    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.strip()

        term_m = _SCRIPT_TERMINAL_RE.search(stripped)
        if term_m:
            command = term_m.group("command").strip()
            output_lines = []
            j = i + 1
            while j < len(lines):
                out_m = _OUTPUT_LINE_RE.match(lines[j])
                if not out_m:
                    break
                output_lines.append(out_m.group("text"))
                j += 1
            order += 1
            entries.append(
                ChecklistEntry(
                    order, None, None, None, _default_command_label(command),
                    "command", command, "\n".join(output_lines),
                )
            )
            i = j
            continue

        m = _SCRIPT_LINE_RE.search(stripped)
        if not m:
            i += 1
            continue

        file_path = m.group("file").strip()
        start_line = int(m.group("start"))
        end_line = int(m.group("end"))
        label = (m.group("inline_label") or "").strip()

        if not label:
            # Fall back to the next non-empty line as a human label.
            for follow in lines[i + 1:]:
                follow = follow.strip().lstrip("#").strip()
                if follow:
                    label = follow[:80]
                    break

        if not label:
            label = _default_label(file_path, start_line, end_line)

        order += 1
        entries.append(ChecklistEntry(order, file_path, start_line, end_line, label))
        i += 1

    if not entries:
        raise ChecklistParseError(
            f"{source_name}: no '[Screenshot] path, lines N-M' or "
            f"'[Terminal] command' entries found"
        )

    return entries


def _default_label(file_path, start_line, end_line):
    import os
    stem = os.path.splitext(os.path.basename(file_path))[0]
    return f"{stem}_{start_line}_{end_line}"


def _default_command_label(command):
    return command.strip()[:60]


# ---------------------------------------------------------------------------
# Format auto-detection
# ---------------------------------------------------------------------------

def load_checklist(path):
    """
    Read a checklist file from disk and parse it, auto-detecting the format:
      - .json extension -> JSON
      - contains a '[Screenshot]' marker -> vlog script format
      - otherwise -> plain text format
    Returns a list of ChecklistEntry, sorted by order.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    lower = path.lower()
    if lower.endswith(".json"):
        return parse_json_checklist(text, source_name=path)

    lower_text = text.lower()
    if "[screenshot]" in lower_text or "[terminal]" in lower_text:
        return extract_from_script(text, source_name=path)

    stripped = text.lstrip()
    if stripped.startswith("["):
        # Looks like JSON even without a .json extension.
        return parse_json_checklist(text, source_name=path)

    return parse_text_checklist(text, source_name=path)
