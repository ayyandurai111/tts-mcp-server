"""SVG -> high-resolution PNG rasterization for `visual_creator`.

Rasterizer choice
-----------------
`resvg` was picked over `cairosvg` for this: resvg's text layout/shaping is
noticeably more accurate for the kind of dense, small-in-source code/terminal
SVGs vlogshot produces (this matters a lot once we're supersampling to 4K -
cairosvg's simpler text shaping tends to show its seams at that scale).
`resvg-py` (pinned in requirements.txt) ships a bundled native resvg build
and installs cleanly via pip in this sandbox (verified: no system `resvg`
CLI or cairo/pango system packages needed), so no CLI subprocess or
apt-level dependency is required. `cairosvg` is kept as a soft runtime
fallback in case `resvg_py` is ever unavailable in a given deployment
environment (e.g. an unsupported wheel platform), so the PNG output feature
degrades gracefully instead of hard-failing.

Both paths render straight from the SVG source to PNG bytes in one call -
there is no intermediate low-res raster at any point.

Font handling - important
--------------------------
vlogshot embeds its code font as a base64 `@font-face` rule (see
app/core/vlogshot/svgkit.py's `font_face_css()`), referencing it under the
made-up family names "VlogshotMono"/"VlogshotMono-Bold". This keeps a
*viewed* SVG self-contained and portable - but resvg's CSS engine
(simplecss) does not implement `@font-face` at all (confirmed: it logs
"The @font-face rule is not supported. Skipped." and then "No match for
'VlogshotMono' font-family"), so a naive `svg_to_bytes()` call silently
falls back to whatever generic system font resvg finds - which is why an
early version of this rasterizer produced text in the wrong (non-monospace)
font instead of vlogshot's actual DejaVu Sans Mono.

The fix: rasterization loads the *real* TTF files straight from vlogshot's
own asset directory via resvg's `font_dirs` option (bypassing @font-face
entirely - resvg's fontdb reads the font files directly and matches by
their real internal family name, "DejaVu Sans Mono", plus font-weight for
bold), and the SVG text is rewritten just before rendering so its
font-family attributes point at that real name instead of the placeholder
one. The @font-face <style> block itself is left alone (harmless no-op for
resvg, and still gives the original SVG file its own portability when
opened directly in a browser, which *does* support @font-face).
"""

from __future__ import annotations

import math
import os
import re

MIN_LONG_EDGE_PX = 3840  # "4K" long edge, per spec.

_WIDTH_RE = re.compile(r'<svg\b[^>]*?\bwidth="([0-9.]+)"')
_HEIGHT_RE = re.compile(r'<svg\b[^>]*?\bheight="([0-9.]+)"')

# vlogshot's own embedded-font asset dir and the made-up family names it
# writes into generated SVGs (see app/core/vlogshot/svgkit.py). The actual
# TTFs' internal family name is "DejaVu Sans Mono" for both weights - only
# font-weight distinguishes regular from bold.
_VLOGSHOT_FONT_DIR = os.path.join(
    os.path.dirname(__file__), "vlogshot", "assets", "fonts"
)
_REAL_FONT_FAMILY = "DejaVu Sans Mono"
_VLOGSHOT_FONT_FAMILY_RE = re.compile(r'font-family="VlogshotMono(-Bold)?"')


def _use_real_font_family(svg_text: str) -> str:
    """Point font-family attributes at the real, on-disk font instead of
    vlogshot's placeholder @font-face name resvg can't resolve.

    "VlogshotMono" -> `font-family="DejaVu Sans Mono"`
    "VlogshotMono-Bold" -> `font-family="DejaVu Sans Mono" font-weight="bold"`
    so resvg's fontdb (loaded via font_dirs, see rasterize_svg_to_png_bytes)
    picks the correct weight from the same real family name.
    """

    def _replace(match: "re.Match[str]") -> str:
        is_bold = match.group(1) is not None
        attrs = f'font-family="{_REAL_FONT_FAMILY}"'
        if is_bold:
            attrs += ' font-weight="bold"'
        return attrs

    return _VLOGSHOT_FONT_FAMILY_RE.sub(_replace, svg_text)


class RasterizeError(RuntimeError):
    """Raised when an SVG string cannot be rasterized to PNG."""


def _svg_source_size(svg_text: str) -> tuple[float, float]:
    """Pull the root `width`/`height` attributes vlogshot always writes.

    vlogshot's SvgDocument always emits an explicit `width="N" height="N"`
    on the root <svg> (see svgkit.py), matching its viewBox 1:1, so a plain
    regex is enough here - no need to pull in a full XML parser just to read
    two attributes off a document we generated ourselves.
    """
    w_match = _WIDTH_RE.search(svg_text)
    h_match = _HEIGHT_RE.search(svg_text)
    if not w_match or not h_match:
        raise RasterizeError(
            "Could not determine source SVG width/height (missing root "
            "width/height attributes)."
        )
    return float(w_match.group(1)), float(h_match.group(1))


def _target_width(source_width: float, source_height: float) -> int:
    """Smallest integer render width that puts the long edge >= 4K.

    Both renderers scale uniformly when given only a target `width` (aspect
    ratio preserved), so applying the same scale factor to source_width -
    regardless of whether width or height is the long edge - is enough to
    guarantee the long edge itself clears MIN_LONG_EDGE_PX.
    """
    long_edge = max(source_width, source_height)
    if long_edge <= 0:
        raise RasterizeError("Source SVG has zero or negative dimensions.")
    scale = max(1.0, MIN_LONG_EDGE_PX / long_edge)
    return math.ceil(source_width * scale)


def rasterize_svg_to_png_bytes(svg_text: str) -> bytes:
    """Render an SVG string to PNG bytes at >=4K on its long edge.

    Renders directly from the SVG source in a single pass (width-only,
    aspect-ratio-preserving), so there is no low-res intermediate to
    upscale. Returns raw PNG bytes ready to write straight to disk.
    """
    source_width, source_height = _svg_source_size(svg_text)
    target_width = _target_width(source_width, source_height)
    svg_text = _use_real_font_family(svg_text)

    try:
        import resvg_py
    except ImportError:
        resvg_py = None

    if resvg_py is not None:
        try:
            return resvg_py.svg_to_bytes(
                svg_string=svg_text,
                width=target_width,
                font_dirs=[_VLOGSHOT_FONT_DIR],
            )
        except Exception as exc:  # noqa: BLE001 - try the cairosvg fallback before giving up
            try:
                return _rasterize_with_cairosvg(svg_text, target_width)
            except Exception:
                raise RasterizeError(f"resvg rendering failed: {exc}") from exc

    try:
        return _rasterize_with_cairosvg(svg_text, target_width)
    except Exception as exc:  # noqa: BLE001
        raise RasterizeError(
            f"PNG rasterization failed (no working rasterizer available): {exc}"
        ) from exc


def _rasterize_with_cairosvg(svg_text: str, target_width: int) -> bytes:
    # cairosvg/pango resolve fonts by real family name via fontconfig, so
    # (unlike resvg) it's enough that the SVG now says "DejaVu Sans Mono" -
    # no explicit font path needed as long as DejaVu is installed as a
    # system font (it ships by default on Debian/Ubuntu as fonts-dejavu-core).
    import cairosvg

    return cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), output_width=target_width)
