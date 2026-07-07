"""
Lenient resolution of a checklist "file" string against the extracted
project tree.

Matching rules (in order):
  1. Exact relative path match (after normalizing slashes and stripping
     a leading "./").
  2. Suffix match: any file in the tree whose path ends with the given
     value on a path-separator boundary.
  3. If multiple suffix matches are found, pick the one with the
     shortest full path (closest to the project root) and report the
     ambiguity so the caller can warn about it.
  4. No match -> None (caller treats this as a hard failure for that entry).
"""

import os
from collections import namedtuple

ResolveResult = namedtuple("ResolveResult", ["path", "ambiguous_candidates"])


def _normalize(p):
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def build_file_index(root_dir):
    """Return a list of all file paths under root_dir, relative to root_dir."""
    index = []
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, root_dir).replace(os.sep, "/")
            index.append(rel)
    return index


def resolve_file(root_dir, requested_path, file_index=None):
    """
    Try to resolve `requested_path` (as written in the checklist) to a real
    file under `root_dir`.

    Returns a ResolveResult(path, ambiguous_candidates):
      - path: resolved path relative to root_dir, or None if not found.
      - ambiguous_candidates: list of other candidate relative paths that
        also matched (empty unless there was ambiguity to warn about).
    """
    if file_index is None:
        file_index = build_file_index(root_dir)

    wanted = _normalize(requested_path)

    # 1. Exact match (case-sensitive first, then case-insensitive fallback).
    for rel in file_index:
        if rel == wanted:
            return ResolveResult(rel, [])

    wanted_lower = wanted.lower()
    for rel in file_index:
        if rel.lower() == wanted_lower:
            return ResolveResult(rel, [])

    # 2. Suffix match on a path-boundary (so "core/tts.py" matches
    #    ".../app/core/tts.py" but not ".../fakecore/tts.py").
    def is_suffix_match(rel):
        rel_l = rel.lower()
        if rel_l == wanted_lower:
            return True
        if rel_l.endswith("/" + wanted_lower):
            return True
        return False

    candidates = [rel for rel in file_index if is_suffix_match(rel)]

    if not candidates:
        return ResolveResult(None, [])

    if len(candidates) == 1:
        return ResolveResult(candidates[0], [])

    # 3. Multiple matches -> shortest path wins, others reported as ambiguous.
    candidates_sorted = sorted(candidates, key=lambda r: (r.count("/"), len(r)))
    chosen = candidates_sorted[0]
    others = candidates_sorted[1:]
    return ResolveResult(chosen, others)
