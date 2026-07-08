"""
Small colored "badge" shown in the tab bar next to the filename, standing
in for a file-type icon. Deliberately generic (colored square + short text)
rather than a copy of any editor's actual icon set/logos.
"""

import os

# ext -> (badge_text, background_color, text_color)
_BADGES = {
    ".py": ("PY", (55, 118, 171), (255, 255, 255)),
    ".pyw": ("PY", (55, 118, 171), (255, 255, 255)),
    ".js": ("JS", (240, 219, 79), (40, 40, 40)),
    ".mjs": ("JS", (240, 219, 79), (40, 40, 40)),
    ".jsx": ("JSX", (240, 219, 79), (40, 40, 40)),
    ".ts": ("TS", (49, 120, 198), (255, 255, 255)),
    ".tsx": ("TSX", (49, 120, 198), (255, 255, 255)),
    ".json": ("{ }", (240, 163, 79), (40, 40, 40)),
    ".yaml": ("YM", (203, 75, 22), (255, 255, 255)),
    ".yml": ("YM", (203, 75, 22), (255, 255, 255)),
    ".md": ("MD", (85, 140, 210), (255, 255, 255)),
    ".markdown": ("MD", (85, 140, 210), (255, 255, 255)),
    ".txt": ("TX", (120, 120, 120), (255, 255, 255)),
    ".html": ("HTM", (227, 79, 38), (255, 255, 255)),
    ".css": ("CSS", (86, 121, 191), (255, 255, 255)),
    ".sh": ("SH", (78, 150, 84), (255, 255, 255)),
    ".java": ("JV", (176, 114, 25), (255, 255, 255)),
    ".go": ("GO", (0, 173, 216), (30, 30, 30)),
    ".rs": ("RS", (222, 128, 82), (40, 40, 40)),
    ".c": ("C", (85, 85, 190), (255, 255, 255)),
    ".cpp": ("C++", (85, 85, 190), (255, 255, 255)),
    ".rb": ("RB", (204, 52, 45), (255, 255, 255)),
    ".sql": ("SQL", (60, 140, 130), (255, 255, 255)),
    ".xml": ("XML", (150, 150, 90), (40, 40, 40)),
}

_DEFAULT_BADGE = ("TXT", (110, 110, 110), (255, 255, 255))


def badge_for_file(file_path):
    """Return (text, bg_color, text_color) for the given file path's extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return _BADGES.get(ext, _DEFAULT_BADGE)
