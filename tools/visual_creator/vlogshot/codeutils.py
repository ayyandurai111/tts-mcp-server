"""
Shared code-handling helpers used by the renderer: lexer detection,
tokenizing source into colored (color, text) runs per line, and small
text-label helpers. No drawing/image logic lives here.
"""

from pygments import lex
from pygments.lexers import (
    get_lexer_for_filename,
    guess_lexer,
    TextLexer,
)
from pygments.util import ClassNotFound


def get_lexer_for_code(file_path, code_text):
    """
    Resolve a Pygments lexer for the given file, falling back gracefully
    to a guess based on content, and finally to plain text.
    """
    try:
        return get_lexer_for_filename(file_path, code_text, stripnl=False)
    except ClassNotFound:
        pass
    try:
        return guess_lexer(code_text, stripnl=False)
    except ClassNotFound:
        pass
    return TextLexer(stripnl=False)


def color_for_token(ttype, theme):
    """Walk up the Pygments token type hierarchy for the first color match."""
    token_colors = theme["token_colors"]
    t = ttype
    while t is not None:
        key = str(t)
        if key in token_colors:
            return token_colors[key]
        t = t.parent
    return theme["default_text"]


def tokenize_into_lines(code_text, lexer, theme):
    """Tokenize `code_text` into a list of lines of (color, text) runs."""
    lines = [[]]
    for ttype, value in lex(code_text, lexer):
        if not value:
            continue
        color = color_for_token(ttype, theme)
        parts = value.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                lines.append([])
            if part:
                lines[-1].append((color, part))

    if lines and not lines[-1] and code_text.endswith("\n"):
        lines.pop()

    return lines


def lang_label(lexer):
    """A short, human status-bar label for the detected language."""
    name = lexer.name
    overrides = {
        "Text only": "Plain Text",
    }
    return overrides.get(name, name)


def repo_and_relpath(file_path):
    """Split a resolved relative path into (top_level_folder_or_None, path)."""
    parts = file_path.replace("\\", "/").split("/")
    if len(parts) > 1:
        return parts[0], file_path
    return None, file_path
