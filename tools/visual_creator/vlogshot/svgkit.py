"""
Shared low-level SVG building blocks used by every renderer (code window,
terminal window, ...): color formatting, font embedding, and a tiny
canvas-like helper for accumulating SVG element strings.

Keeping this in one place means every renderer produces vector output with
the same embedded-font approach — so screenshots look identical wherever
they're opened, and nothing ever pixelates when zoomed in.
"""

import base64
import os
from xml.sax.saxutils import escape as xml_escape

ASSETS_FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")

_FONT_FILES = {
    False: "DejaVuSansMono.ttf",
    True: "DejaVuSansMono-Bold.ttf",
}
_FONT_FAMILY = {False: "VlogshotMono", True: "VlogshotMono-Bold"}


def rgb(color):
    return f"rgb({color[0]},{color[1]},{color[2]})"


def _b64_font(bold):
    path = os.path.join(ASSETS_FONT_DIR, _FONT_FILES[bold])
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def font_face_css():
    faces = []
    for bold in (False, True):
        data = _b64_font(bold)
        faces.append(
            f"@font-face {{ font-family: '{_FONT_FAMILY[bold]}'; "
            f"src: url(data:font/ttf;base64,{data}) format('truetype'); }}"
        )
    return "\n".join(faces)


def load_measure_font(size, bold=False):
    from PIL import ImageFont

    name = _FONT_FILES[bold]
    return ImageFont.truetype(os.path.join(ASSETS_FONT_DIR, name), size)


class Svg:
    """Tiny helper for accumulating SVG element strings."""

    def __init__(self):
        self.parts = []

    def rect(self, x, y, w, h, fill, opacity=None):
        op = f' fill-opacity="{opacity}"' if opacity is not None else ""
        self.parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="{rgb(fill)}"{op}/>'
        )

    def rrect(self, x, y, w, h, r, fill):
        self.parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'rx="{r:.2f}" ry="{r:.2f}" fill="{rgb(fill)}"/>'
        )

    def circle(self, cx, cy, r, fill):
        self.parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{rgb(fill)}"/>')

    def line(self, x1, y1, x2, y2, stroke, width=1):
        self.parts.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{rgb(stroke)}" stroke-width="{width:.2f}"/>'
        )

    def text(self, x, y, s, font_size, fill, bold=False, anchor="start",
              text_length=None):
        if not s:
            return
        family = _FONT_FAMILY[bold]
        extra = ""
        if text_length is not None and text_length > 0:
            extra = f' textLength="{text_length:.2f}" lengthAdjust="spacingAndGlyphs"'
        self.parts.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-family="{family}" '
            f'font-size="{font_size:.2f}" fill="{rgb(fill)}" '
            f'text-anchor="{anchor}" xml:space="preserve"{extra}>'
            f'{xml_escape(s)}</text>'
        )

    def group(self, inner_parts):
        self.parts.extend(inner_parts)

    def render(self, width, height, background):
        header = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
            f'<style>{font_face_css()}</style>'
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="{rgb(background)}"/>'
        )
        return header + "".join(self.parts) + "</svg>"
