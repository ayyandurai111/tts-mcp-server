from __future__ import annotations

import io

import pytest
from PIL import Image

from tools.visual_creator.rasterize import rasterize_svg_to_png_bytes, RasterizeError


def _monospace_svg(text: str, bold: bool = False) -> str:
    family = "VlogshotMono-Bold" if bold else "VlogshotMono"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="200" '
        'viewBox="0 0 1200 200">'
        '<rect width="1200" height="200" fill="#000000"/>'
        f'<text x="10" y="120" font-family="{family}" font-size="60" '
        f'fill="#ffffff">{text}</text>'
        "</svg>"
    )


def _rendered_glyph_run_width(png_bytes: bytes) -> int:
    """Pixel column span of any non-background (bright) content."""
    img = Image.open(io.BytesIO(png_bytes)).convert("L")
    width, height = img.size
    pixels = img.load()
    lit_columns = [
        x
        for x in range(width)
        if any(pixels[x, y] > 20 for y in range(height))
    ]
    return (max(lit_columns) - min(lit_columns)) if lit_columns else 0


def test_rasterized_text_uses_the_real_monospace_font_not_a_fallback():
    """Regression test for the wrong-font bug: vlogshot's SVGs reference the
    font only via a made-up @font-face family name ("VlogshotMono"), which
    resvg's CSS engine cannot resolve (it doesn't implement @font-face at
    all). Rasterizing must rewrite that to the real on-disk font
    ("DejaVu Sans Mono", loaded via font_dirs) rather than silently falling
    back to some proportional system font. A true monospace font renders
    every character to the same width; a proportional fallback (what this
    bug used to produce) does not.
    """
    narrow_width = _rendered_glyph_run_width(rasterize_svg_to_png_bytes(_monospace_svg("i" * 10)))
    wide_width = _rendered_glyph_run_width(rasterize_svg_to_png_bytes(_monospace_svg("m" * 10)))

    assert narrow_width > 0 and wide_width > 0
    # Allow a little antialiasing/measurement slack, but a proportional
    # fallback font would show roughly a 2-3x difference here, not ~5%.
    assert abs(narrow_width - wide_width) / wide_width < 0.15


def test_bold_variant_also_resolves_without_error():
    png_bytes = rasterize_svg_to_png_bytes(_monospace_svg("Bold Test", bold=True))
    with Image.open(io.BytesIO(png_bytes)) as img:
        assert img.format == "PNG"
        assert img.size[0] >= 1200


def test_rasterize_raises_on_missing_dimensions():
    with pytest.raises(RasterizeError):
        rasterize_svg_to_png_bytes("<svg><rect/></svg>")
