"""
Rendering of a slice of source code into a clean, editor-style SVG.

Two styles are supported:

  "vscode"  (default) — a full VS Code-style window: title bar, tab bar
            with a language badge, breadcrumb path, gutter + code,
            a lightweight minimap, and a status bar.

  "minimal" — just a dark header bar with the file path, plus gutter + code.

Output is vector SVG, not a rasterized pixel grid, so it never blurs or
pixelates no matter how far you zoom in. The DejaVu Sans Mono fonts are
embedded directly in the SVG (as base64 @font-face data) so the screenshot
looks identical everywhere it's opened, regardless of which fonts are
installed on the viewing machine. Every text element also sets
textLength/lengthAdjust so character alignment (gutter, columns, minimap)
stays exact even if a viewer ever falls back to a different font.
"""

import os

from PIL import ImageFont

from .codeutils import get_lexer_for_code, tokenize_into_lines, lang_label, repo_and_relpath
from .themes import get_theme
from .badges import badge_for_file
from .svgkit import Svg, ASSETS_FONT_DIR, load_measure_font

IMAGE_WIDTH = 1920
DEFAULT_FONT_SIZE = 22

PADDING_X = 28
PADDING_TOP = 14
PADDING_BOTTOM = 18
LINE_HEIGHT_FACTOR = 1.5

GUTTER_PADDING = 22
GUTTER_RIGHT_PAD = 18

TITLE_BAR_HEIGHT = 32
TAB_BAR_HEIGHT = 36
BREADCRUMB_HEIGHT = 26
STATUS_BAR_HEIGHT = 24

MINIMAP_WIDTH = 84
MINIMAP_LINE_HEIGHT = 3
MINIMAP_CHAR_WIDTH = 1.6

MIN_CODE_AREA_WIDTH = 320

# Fixed output canvas size. Every screenshot is rendered onto this exact
# height regardless of line count, so a batch of screenshots dropped into a
# video timeline never changes dimensions between clips. Code always starts
# at the top (right under the chrome), like a real editor; short snippets
# just leave empty space at the bottom. Snippets too long to fit are
# paginated by the caller into multiple same-sized screenshots instead of
# shrinking font/line-height to cram everything in.
DEFAULT_IMAGE_HEIGHT = 1080



def max_lines_per_page(
    font_size=DEFAULT_FONT_SIZE,
    style="vscode",
    image_height=DEFAULT_IMAGE_HEIGHT,
):
    """
    How many lines of code fit in one fixed-size canvas at this font size
    and style, before pagination is needed. Used by callers to split a long
    snippet into multiple same-sized screenshots up front, rather than
    rendering once and finding out it overflowed.
    """
    fs = font_size
    use_chrome = style == "vscode"

    title_h = TITLE_BAR_HEIGHT if use_chrome else 0
    tab_h = TAB_BAR_HEIGHT if use_chrome else 0
    breadcrumb_h = BREADCRUMB_HEIGHT if use_chrome else 0
    status_h = STATUS_BAR_HEIGHT if use_chrome else 0
    minimal_header_h = (max(font_size - 4, 12) + 24) if not use_chrome else 0

    code_font = ImageFont.truetype(os.path.join(ASSETS_FONT_DIR, "DejaVuSansMono.ttf"), fs)
    ascent, descent = code_font.getmetrics()
    line_height = int((ascent + descent) * LINE_HEIGHT_FACTOR)

    chrome_h = title_h + tab_h + breadcrumb_h + minimal_header_h + status_h
    available = image_height - chrome_h - PADDING_TOP - PADDING_BOTTOM
    return max(1, available // line_height)


def render_code_screenshot(
    code_text,
    file_path,
    start_line,
    out_path,
    theme_name="dark",
    font_size=DEFAULT_FONT_SIZE,
    image_width=IMAGE_WIDTH,
    style="vscode",
    image_height=DEFAULT_IMAGE_HEIGHT,
):
    """
    Render `code_text` to a vector SVG at `out_path`. Same parameters and
    layout as render_code_screenshot() in render.py, minus `scale` (vector
    output has no need for supersampling — it's resolution-independent and
    won't pixelate when zoomed).

    The output canvas is always exactly `image_width` x `image_height`
    (default 1920x1080), regardless of how many lines `code_text` has. Code
    always starts at the top, right under the title/tab/breadcrumb chrome
    (like a real editor); fewer lines just leave empty space at the bottom
    of the fixed canvas. Lines that don't fit are clipped at the bottom
    edge. Callers that don't want clipping should pre-split long code using
    `max_lines_per_page()` — `render_code_pages()` below does this
    automatically.
    """
    theme = get_theme(theme_name)
    lexer = get_lexer_for_code(file_path, code_text)

    lines = tokenize_into_lines(code_text, lexer, theme)
    if not lines:
        lines = [[]]
    num_lines = len(lines)
    last_line_no = start_line + num_lines - 1
    gutter_digits = max(len(str(last_line_no)), 2)

    W = image_width
    fs = font_size
    header_fs = max(font_size - 4, 12)
    small_fs = max(font_size - 6, 11)

    pad_x = PADDING_X
    pad_top = PADDING_TOP
    pad_bottom = PADDING_BOTTOM
    gutter_pad = GUTTER_PADDING
    gutter_right_pad = GUTTER_RIGHT_PAD

    use_chrome = style == "vscode"
    show_minimap = use_chrome and (image_width - MINIMAP_WIDTH) >= MIN_CODE_AREA_WIDTH

    title_h = TITLE_BAR_HEIGHT if use_chrome else 0
    tab_h = TAB_BAR_HEIGHT if use_chrome else 0
    breadcrumb_h = BREADCRUMB_HEIGHT if use_chrome else 0
    status_h = STATUS_BAR_HEIGHT if use_chrome else 0
    minimal_header_h = (max(font_size - 4, 12) + 24) if not use_chrome else 0

    minimap_w = MINIMAP_WIDTH if show_minimap else 0

    # Metrics only — Pillow is used solely to measure text, nothing is rasterized.
    code_font = ImageFont.truetype(os.path.join(ASSETS_FONT_DIR, "DejaVuSansMono.ttf"), fs)
    from PIL import Image, ImageDraw
    _measure = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    char_width = _measure.textlength("0", font=code_font)
    ascent, descent = code_font.getmetrics()
    line_height = int((ascent + descent) * LINE_HEIGHT_FACTOR)

    gutter_width = int(gutter_digits * char_width + gutter_pad + gutter_right_pad)

    chrome_top_h = title_h + tab_h + breadcrumb_h + minimal_header_h
    code_text_height = num_lines * line_height

    # Always start code right under the chrome (title/tab/breadcrumb bar),
    # like a real editor — short snippets leave the leftover space at the
    # bottom of the fixed canvas rather than floating in the middle. Long
    # snippets simply run further down (and, if taller than the canvas,
    # clip at the bottom — the caller should have paginated before that
    # happens).
    code_top = chrome_top_h + pad_top
    code_bottom = code_top + code_text_height + pad_bottom
    total_height = image_height

    svg = Svg()

    if use_chrome:
        _draw_title_bar(svg, theme, W, title_h, file_path, header_fs, _measure)
        _draw_tab_bar(svg, theme, W, title_h, tab_h, file_path, header_fs, small_fs, _measure)
        _draw_breadcrumbs(svg, theme, W, title_h + tab_h, breadcrumb_h, file_path, small_fs, _measure)
    else:
        _draw_minimal_header(svg, theme, W, minimal_header_h, file_path, header_fs, _measure)

    divider_y_top = title_h + tab_h + breadcrumb_h + minimal_header_h
    svg.line(gutter_width, divider_y_top, gutter_width, code_bottom, theme["gutter_divider"], width=1)

    y = code_top
    code_x_start = gutter_width + pad_x // 2
    code_area_right = W - minimap_w
    baseline_offset = ascent  # y for draw.text is top-left in PIL; SVG text y is baseline

    for idx, line_runs in enumerate(lines):
        line_no = start_line + idx
        line_no_str = str(line_no)
        num_w = _measure.textlength(line_no_str, font=code_font)
        num_x = gutter_width - gutter_right_pad - num_w
        svg.text(num_x, y + baseline_offset, line_no_str, fs, theme["gutter_text"],
                  text_length=num_w)

        x = code_x_start
        for color, text_run in line_runs:
            run_w = _measure.textlength(text_run, font=code_font)
            if x < code_area_right:
                svg.text(x, y + baseline_offset, text_run, fs, color, text_length=run_w)
            x += run_w

        y += line_height

    if show_minimap:
        _draw_minimap(svg, theme, code_area_right, minimap_w, code_top, code_bottom, lines)

    if use_chrome:
        # Pinned to the bottom of the fixed canvas (like a real editor
        # window), not directly under the code block, so it stays in the
        # same place across every screenshot regardless of line count.
        status_bar_top = image_height - status_h
        _draw_status_bar(svg, theme, W, status_bar_top, status_h, lexer, start_line,
                          num_lines, small_fs, _measure)

    svg_text = svg.render(W, total_height, theme["background"])
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg_text)
    return out_path


def render_code_pages(
    code_text,
    file_path,
    start_line,
    out_path_pattern,
    theme_name="dark",
    font_size=DEFAULT_FONT_SIZE,
    image_width=IMAGE_WIDTH,
    style="vscode",
    image_height=DEFAULT_IMAGE_HEIGHT,
):
    """
    Render `code_text` as one or more fixed-size (image_width x
    image_height) SVG screenshots, splitting across multiple pages if the
    snippet has more lines than fit on one canvas at this font size.

    This is the pagination counterpart to `render_code_screenshot()`: that
    function will silently clip if given too much code for one canvas, this
    function instead automatically breaks a long snippet into as many
    same-sized pages as needed, each with correct gutter line numbers
    continuing on from the previous page, and no page ever overflows the
    fixed canvas.

    `out_path_pattern` is a path containing a single "{page}" placeholder,
    e.g. "output/01_foo_{page}.svg". For a single-page result "{page}" is
    replaced with "" (so a short snippet's filename is unchanged); for
    multi-page results it's replaced with "_p1", "_p2", etc.

    Returns the list of output paths written, in page order.
    """
    lines_per_page = max_lines_per_page(font_size=font_size, style=style, image_height=image_height)

    all_lines = code_text.splitlines(keepends=True)
    if not all_lines:
        all_lines = [""]

    total_lines = len(all_lines)
    num_pages = max(1, (total_lines + lines_per_page - 1) // lines_per_page)

    out_paths = []
    for page_idx in range(num_pages):
        page_start = page_idx * lines_per_page
        page_end = min(page_start + lines_per_page, total_lines)
        page_code = "".join(all_lines[page_start:page_end])
        if page_code and not page_code.endswith("\n"):
            page_code += "\n"

        suffix = "" if num_pages == 1 else f"_p{page_idx + 1}"
        out_path = out_path_pattern.format(page=suffix)

        render_code_screenshot(
            page_code,
            file_path=file_path,
            start_line=start_line + page_start,
            out_path=out_path,
            theme_name=theme_name,
            font_size=font_size,
            image_width=image_width,
            style=style,
            image_height=image_height,
        )
        out_paths.append(out_path)

    return out_paths


# ---------------------------------------------------------------------------
# Chrome drawing helpers (mirror render.py's, output SVG instead of pixels)
# ---------------------------------------------------------------------------

def _load_measure_font(measure, size, bold=False):
    return load_measure_font(size, bold=bold)


def _draw_minimal_header(svg, theme, width, height, file_path, header_fs, measure):
    svg.rect(0, 0, width, height, theme["header_bg"])

    font = _load_measure_font(measure, header_fs)
    text_x = height * 0.5
    ascent, descent = font.getmetrics()
    text_y = height / 2 + (ascent - descent) / 2
    svg.text(text_x, text_y, file_path, header_fs, theme["header_text"])


def _draw_title_bar(svg, theme, width, height, file_path, header_fs, measure):
    svg.rect(0, 0, width, height, theme["titlebar_bg"])

    repo, _ = repo_and_relpath(file_path)
    filename = file_path.rsplit("/", 1)[-1]
    title_text = f"{filename} \u2014 {repo}" if repo else filename

    font = _load_measure_font(measure, header_fs)
    text_w = measure.textlength(title_text, font=font)
    ascent, descent = font.getmetrics()
    text_x = (width - text_w) / 2
    text_y = height / 2 + (ascent - descent) / 2
    svg.text(text_x, text_y, title_text, header_fs, theme["titlebar_text"], text_length=text_w)


def _draw_tab_bar(svg, theme, width, top, height, file_path, header_fs, small_fs, measure):
    svg.rect(0, top, width, height, theme["tabbar_bg"])

    filename = file_path.rsplit("/", 1)[-1]
    badge_text, badge_bg, badge_fg = badge_for_file(file_path)

    header_font = _load_measure_font(measure, header_fs)
    badge_font = _load_measure_font(measure, int(small_fs * 0.92), bold=True)

    tab_pad_x = 16
    badge_pad = 8
    badge_h = height * 0.5
    badge_w = max(badge_h, measure.textlength(badge_text, font=badge_font) + 10)

    name_w = measure.textlength(filename, font=header_font)
    close_w = 18
    tab_w = tab_pad_x + badge_w + badge_pad + name_w + 14 + close_w + tab_pad_x

    svg.rect(0, top, tab_w, height, theme["tab_active_bg"])
    border_h = 2
    svg.rect(0, top, tab_w, border_h, theme["tab_active_border"])

    cy = top + height / 2

    bx0 = tab_pad_x
    by0 = cy - badge_h / 2
    bx1 = bx0 + badge_w
    radius = 3
    svg.rrect(bx0, by0, badge_w, badge_h, radius, badge_bg)
    b_ascent, b_descent = badge_font.getmetrics()
    svg.text(bx0 + badge_w / 2, cy + (b_ascent - b_descent) / 2, badge_text,
              int(small_fs * 0.92), badge_fg, bold=True, anchor="middle")

    name_x = bx1 + badge_pad
    n_ascent, n_descent = header_font.getmetrics()
    svg.text(name_x, cy + (n_ascent - n_descent) / 2, filename, header_fs,
              theme["tab_active_text"], text_length=name_w)

    close_x_center = name_x + name_w + 14
    close_r = 6
    svg.line(close_x_center - close_r, cy - close_r, close_x_center + close_r, cy + close_r,
              theme["tab_inactive_text"], width=1)
    svg.line(close_x_center - close_r, cy + close_r, close_x_center + close_r, cy - close_r,
              theme["tab_inactive_text"], width=1)


def _draw_breadcrumbs(svg, theme, width, top, height, file_path, small_fs, measure):
    svg.rect(0, top, width, height, theme["breadcrumb_bg"])

    font = _load_measure_font(measure, small_fs)
    parts = file_path.replace("\\", "/").split("/")
    x = 14
    cy = top + height / 2
    sep = " \u203a "
    ascent, descent = font.getmetrics()
    text_y = cy + (ascent - descent) / 2

    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        color = theme["breadcrumb_text_last"] if is_last else theme["breadcrumb_text"]
        w = measure.textlength(part, font=font)
        svg.text(x, text_y, part, small_fs, color, text_length=w)
        x += w
        if not is_last:
            sw = measure.textlength(sep, font=font)
            svg.text(x, text_y, sep, small_fs, theme["breadcrumb_sep"], text_length=sw)
            x += sw


def _draw_minimap(svg, theme, x_start, width, top, bottom, lines):
    svg.rect(x_start, top, width, bottom - top, theme["minimap_bg"])

    row_h = max(1, MINIMAP_LINE_HEIGHT)
    char_w = MINIMAP_CHAR_WIDTH
    left_pad = 6
    max_w = width - left_pad

    y = top
    for line_runs in lines:
        if y >= bottom:
            break
        x = x_start + left_pad
        for color, text_run in line_runs:
            visible = text_run.strip(" ")
            leading = len(text_run) - len(text_run.lstrip(" "))
            if leading:
                x += leading * char_w
            if not visible:
                continue
            avail = max_w - (x - x_start - left_pad)
            block_w = min(avail, len(visible) * char_w)
            if block_w > 0:
                svg.rect(x, y, block_w, max(1, row_h - 1), color)
            x += len(visible) * char_w
        y += row_h

    overlay_h = bottom - top
    alpha = theme.get("minimap_slider_alpha", 16) / 255.0
    svg.rect(x_start, top, width, overlay_h, theme["minimap_slider"], opacity=alpha)


def _draw_status_bar(svg, theme, width, top, height, lexer, start_line, num_lines, small_fs, measure):
    svg.rect(0, top, width, height, theme["statusbar_bg"])

    font = _load_measure_font(measure, small_fs)
    ascent, descent = font.getmetrics()
    cy = top + height / 2
    text_y = cy + (ascent - descent) / 2
    pad = 14

    x = pad

    def draw_left(text, x):
        w = measure.textlength(text, font=font)
        svg.text(x, text_y, text, small_fs, theme["statusbar_text"], text_length=w)
        return x + w

    x = draw_left("\u2387 main", x) + 20
    x = draw_left("\u2713 0   \u25b2 0", x)

    end_line = start_line + num_lines - 1
    lang = lang_label(lexer)
    right_items = [f"Ln {end_line}, Col 1", "Spaces: 4", "UTF-8", "LF", lang]
    rx = width - pad
    for item in reversed(right_items):
        w = measure.textlength(item, font=font)
        rx -= w
        svg.text(rx, text_y, item, small_fs, theme["statusbar_text"], text_length=w)
        rx -= 20
