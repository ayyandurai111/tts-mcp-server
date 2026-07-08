"""
Rendering of a command + its captured output into a Windows Command
Prompt (cmd.exe) -style SVG — the counterpart to render.py's editor-window
screenshots, for the "ran this command, here's what it printed" beats of
a coding vlog.

Matches real cmd.exe as closely as a bundled open-source font allows:
  - black console background, light gray text (the classic default
    16-color "Campbell" scheme Windows has used since Windows 10)
  - "C:\\path>command" prompt with no special coloring (cmd.exe doesn't
    color the prompt or the typed command — it's all one plain-text line)
  - a flat Windows-style title bar with minimize / maximize / close glyphs

Note: cmd.exe's real font is Consolas, a proprietary Microsoft font that
can't legally be bundled/embedded here. This renders with the same bundled
monospace font used elsewhere in this tool, sized and colored to match —
visually very close, but not pixel-identical to a real Consolas capture.

Like the code renderer, output is vector SVG with the font embedded, so it
never pixelates when zoomed and looks identical wherever it's opened.

Basic ANSI SGR color codes in the output are recognized and mapped to the
real Windows Console 16-color palette. Unrecognized/unsupported escape
sequences are stripped rather than shown as garbage text.
"""

import re

from .svgkit import Svg, load_measure_font

IMAGE_WIDTH = 1200
DEFAULT_FONT_SIZE = 20  # visually matches "Consolas 16" in a real console

PADDING_X = 10
PADDING_TOP = 10
PADDING_BOTTOM = 10
LINE_HEIGHT_FACTOR = 1.25  # cmd.exe uses tight single-spaced lines

TITLE_BAR_HEIGHT = 30

DEFAULT_PROMPT = ">"
DEFAULT_CWD = r"C:\Users\You"
DEFAULT_TITLE = "Command Prompt"

# Real cmd.exe console colors (Windows 10+ default "Campbell" scheme).
CONSOLE_BLACK = (12, 12, 12)
CONSOLE_GRAY = (204, 204, 204)  # default foreground ("Gray", color 7)

BACKGROUND = CONSOLE_BLACK
TEXT_COLOR = CONSOLE_GRAY

# Flat Windows 10/11-style light title bar (default light theme).
TITLEBAR_BG = (240, 240, 240)
TITLEBAR_TEXT = (20, 20, 20)
TITLEBAR_BUTTON = (60, 60, 60)

# Standard 16-color Windows Console ("Campbell") palette, keyed by the
# ANSI SGR codes most CLI tools use to select them.
_ANSI_COLORS = {
    30: (12, 12, 12), 31: (197, 15, 31), 32: (19, 161, 14), 33: (193, 156, 0),
    34: (0, 55, 218), 35: (136, 23, 152), 36: (58, 150, 221), 37: (204, 204, 204),
    90: (118, 118, 118), 91: (231, 72, 86), 92: (22, 198, 12), 93: (249, 241, 165),
    94: (59, 120, 255), 95: (180, 0, 158), 96: (97, 214, 214), 97: (242, 242, 242),
}

_ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")


def _parse_ansi_line(line, default_color):
    """
    Split one line of (possibly ANSI-colored) text into a list of
    (color, text) runs, stripping the escape codes themselves. cmd.exe
    doesn't render bold as a separate font weight, so there's no bold
    tracking here — SGR bold (1) is ignored rather than faked.
    """
    runs = []
    color = default_color
    pos = 0
    for m in _ANSI_RE.finditer(line):
        if m.start() > pos:
            runs.append((color, line[pos:m.start()]))
        codes = [c for c in m.group(1).split(";") if c != ""]
        if not codes:
            codes = ["0"]
        for code in codes:
            n = int(code)
            if n == 0:
                color = default_color
            elif n == 39:
                color = default_color
            elif n in _ANSI_COLORS:
                color = _ANSI_COLORS[n]
        pos = m.end()
    if pos < len(line):
        runs.append((color, line[pos:]))
    return runs or [(default_color, "")]


def _draw_terminal_icon(svg, x, y, size):
    """
    A small generic terminal icon: a dark rounded square with a ">_"
    prompt glyph, drawn as plain vector shapes. This is a generic "this
    is a terminal" symbol used by many console apps — not a copy of any
    specific application's actual icon artwork.
    """
    r = size * 0.2
    svg.rrect(x, y, size, size, r, (10, 10, 10))

    glyph_color = (90, 220, 90)
    pad = size * 0.22
    mid_y = y + size / 2
    chevron_w = size * 0.30
    chevron_h = size * 0.30

    # ">" chevron
    svg.line(x + pad, mid_y - chevron_h / 2, x + pad + chevron_w, mid_y, glyph_color, width=1.6)
    svg.line(x + pad + chevron_w, mid_y, x + pad, mid_y + chevron_h / 2, glyph_color, width=1.6)

    # "_" cursor
    underscore_y = y + size - pad * 0.9
    svg.line(
        x + pad + chevron_w + 1.5, underscore_y,
        x + size - pad * 0.8, underscore_y,
        glyph_color, width=1.6,
    )


def _draw_window_controls(svg, width):
    """Minimize / maximize / close glyphs, right-aligned in the title bar."""
    btn_w = 46
    cx_close = width - btn_w / 2
    cx_max = cx_close - btn_w
    cx_min = cx_max - btn_w
    cy = TITLE_BAR_HEIGHT / 2

    # minimize: short horizontal line
    svg.line(cx_min - 5, cy + 5, cx_min + 5, cy + 5, TITLEBAR_BUTTON, width=1.2)

    # maximize: small square outline
    r = 5
    svg.line(cx_max - r, cy - r, cx_max + r, cy - r, TITLEBAR_BUTTON, width=1.2)
    svg.line(cx_max - r, cy + r, cx_max + r, cy + r, TITLEBAR_BUTTON, width=1.2)
    svg.line(cx_max - r, cy - r, cx_max - r, cy + r, TITLEBAR_BUTTON, width=1.2)
    svg.line(cx_max + r, cy - r, cx_max + r, cy + r, TITLEBAR_BUTTON, width=1.2)

    # close: X
    svg.line(cx_close - r, cy - r, cx_close + r, cy + r, TITLEBAR_BUTTON, width=1.2)
    svg.line(cx_close - r, cy + r, cx_close + r, cy - r, TITLEBAR_BUTTON, width=1.2)


def render_terminal_screenshot(
    command,
    output_text,
    out_path,
    prompt=DEFAULT_PROMPT,
    cwd_label=DEFAULT_CWD,
    title=DEFAULT_TITLE,
    font_size=DEFAULT_FONT_SIZE,
    image_width=IMAGE_WIDTH,
):
    """
    Render a Windows Command Prompt-style screenshot showing `command`
    typed at "{cwd_label}{prompt}", followed by `output_text` (its
    captured stdout/stderr), to `out_path` as an SVG. ANSI color codes in
    `output_text` are mapped to the real Windows Console 16-color palette.

    `cwd_label` defaults to a generic "C:\\Users\\You" and `prompt` to ">",
    matching a real cmd.exe prompt ("C:\\Users\\You>"). `title` is the
    window title bar text (default: "Command Prompt").
    """
    fs = font_size
    W = image_width

    font = load_measure_font(fs)
    ascent, descent = font.getmetrics()
    line_height = int((ascent + descent) * LINE_HEIGHT_FACTOR)
    baseline_offset = ascent

    from PIL import Image, ImageDraw
    measure = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    output_lines = output_text.splitlines() if output_text else []
    # One prompt line + one line per output line (blank output -> just the prompt).
    num_lines = 1 + len(output_lines)

    body_top = TITLE_BAR_HEIGHT + PADDING_TOP
    body_height = num_lines * line_height
    total_height = int(body_top + body_height + PADDING_BOTTOM)

    svg = Svg()

    # --- title bar ----------------------------------------------------------
    svg.rect(0, 0, W, TITLE_BAR_HEIGHT, TITLEBAR_BG)
    icon_size = 16
    icon_x = 10
    icon_y = (TITLE_BAR_HEIGHT - icon_size) / 2
    _draw_terminal_icon(svg, icon_x, icon_y, icon_size)

    title_text = title or DEFAULT_TITLE
    t_ascent, t_descent = font.getmetrics()
    svg.text(
        icon_x + icon_size + 10, TITLE_BAR_HEIGHT / 2 + (t_ascent - t_descent) / 2,
        title_text, fs * 0.7, TITLEBAR_TEXT,
    )
    _draw_window_controls(svg, W)

    # --- prompt line: "{cwd}{prompt}{command}", all one plain-text run -----
    x = PADDING_X
    y = body_top

    prompt_line = f"{cwd_label}{prompt}{command}"
    line_w = measure.textlength(prompt_line, font=font)
    svg.text(x, y + baseline_offset, prompt_line, fs, TEXT_COLOR, text_length=line_w)
    y += line_height

    # --- output lines --------------------------------------------------------
    for raw_line in output_lines:
        runs = _parse_ansi_line(raw_line, TEXT_COLOR)
        x = PADDING_X
        for color, text in runs:
            if not text:
                continue
            w = measure.textlength(text, font=font)
            svg.text(x, y + baseline_offset, text, fs, color, text_length=w)
            x += w
        y += line_height

    svg_text = svg.render(W, total_height, BACKGROUND)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg_text)
    return out_path
