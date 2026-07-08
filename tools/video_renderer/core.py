"""Core logic for the `video_renderer` tool.

Turns a project's manifest (see common/project_store.py) - an ordered list
of {audio, visual} pairs - into a single MP4 by shelling out to `ffmpeg`,
the same way app/core/rasterize.py shells out to an external renderer:
pure functions, plain args in, a result dict out, a dedicated exception
raised on failure, no sys.exit.

Pipeline
--------
For each manifest order that has both audio and visual:
  1. One or more still image(s) (visual.filenames) are held on screen for
     that order's audio duration and combined with audio.mp3 into a short
     segment .mp4 (image(s) -> H.264 video + AAC audio).
  2. If an order's visual was paginated (multiple filenames, e.g. a long
     code snippet split into visual_p1.png, visual_p2.png, ...), that
     order's audio duration is split evenly across the pages (see
     "Pagination duration split" below) and each page becomes its own
     sub-segment, image-held for its share of the duration, all sharing
     the same audio track sliced to match.

All segments are then concatenated in `order` sequence into the final
video. Two transition styles are supported:
  - "cut" (default): ffmpeg's concat demuxer stitches segment files
    losslessly (stream copy) with a hard cut between them. This is the
    v1 default because it's the only style with no filter-graph surprises
    and no risk of drifting audio/video sync across many segments.
  - "crossfade": segments are joined with `xfade`/`acrossfade` filters
    (CROSSFADE_SECONDS long, see app/config.py) instead of a concat
    demuxer, at the cost of a full re-encode and a small amount of
    shortening (each transition overlaps two segments, so total duration
    is `sum(segment_durations) - (n-1) * crossfade_seconds`).

Pagination duration split
--------------------------
Manifest metadata doesn't currently carry a per-page content-length or
word-count signal for paginated visuals (visual_creator's manifest entry
only records `visual.filenames`, not a breakdown of how much code/text is
on each page) - so there's nothing more informed to split by. Splitting
the order's audio duration *evenly* across pages is therefore the
documented v1 choice; a future version could weight this by e.g. each
page's on-screen line count if that's ever added to the manifest.

Resolution
----------
v1 requires every order's visual to share one resolution (recommended in
the build spec, since visual_creator already renders a whole batch onto a
fixed canvas size) - mismatched per-order resolutions raise
VideoRenderError rather than silently letterboxing/scaling, so a caller
notices a real inconsistency instead of getting a subtly-wrong video.

Background music mixing is out of scope for v1 - documented as a future
extension, not implemented here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from common.config import (
    CROSSFADE_SECONDS,
    DEFAULT_TRANSITION,
    FFMPEG_BINARY,
    RENDER_TIMEOUT_SECONDS,
)

TRANSITION_STYLES = ("cut", "crossfade")


class VideoRenderError(ValueError):
    """Raised for bad input, missing ffmpeg, or a failed/corrupt render."""


# ---------------------------------------------------------------------------
# ffmpeg availability + low-level subprocess helpers
# ---------------------------------------------------------------------------

def ffmpeg_available() -> bool:
    """Whether the configured ffmpeg binary can actually be found/run."""
    return shutil.which(FFMPEG_BINARY) is not None


def _run_ffmpeg(args: list[str], step: str) -> None:
    """Run one ffmpeg subprocess, raising VideoRenderError with the
    step name + captured stderr tail on any non-zero exit, timeout, or
    missing binary - mirrors rasterize.py's "normalize every failure mode
    into one custom exception" pattern, just for a subprocess instead of
    a library call.
    """
    if not ffmpeg_available():
        raise VideoRenderError(
            f"ffmpeg is not available on this deployment (looked for "
            f"'{FFMPEG_BINARY}' on PATH). Cannot run step: {step}."
        )

    cmd = [FFMPEG_BINARY, "-y", "-hide_banner", "-loglevel", "error", *args]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=RENDER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoRenderError(
            f"ffmpeg timed out after {RENDER_TIMEOUT_SECONDS}s during: {step}."
        ) from exc
    except OSError as exc:
        raise VideoRenderError(f"Failed to launch ffmpeg during: {step}. ({exc})") from exc

    if proc.returncode != 0:
        stderr_tail = proc.stderr.decode("utf-8", errors="replace")[-2000:]
        raise VideoRenderError(f"ffmpeg failed during: {step}.\n{stderr_tail}")


def probe_duration_seconds(path: Path) -> Optional[float]:
    """Best-effort media duration via ffmpeg itself. Returns None on
    failure - callers that already have a manifest-recorded duration
    should prefer that and only fall back to probing.

    Deliberately uses `ffmpeg -i` (parsing stderr) rather than `ffprobe`:
    imageio-ffmpeg (see app/config.py's FFMPEG_BINARY resolution, needed
    because this deploys on a Dockerfile-less PaaS runtime) only ships an
    ffmpeg binary, no ffprobe, so a dedicated ffprobe call can't be relied
    on to exist alongside whatever FFMPEG_BINARY resolves to.
    """
    if not ffmpeg_available():
        return None
    try:
        proc = subprocess.run(
            [FFMPEG_BINARY, "-i", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    # ffmpeg always exits non-zero here (no output file given) - the
    # duration is in its stderr probe/banner output regardless, e.g.
    # "Duration: 00:00:06.80, start: 0.000000, bitrate: ...".
    stderr = proc.stderr.decode("utf-8", errors="replace")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    total = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return round(total, 3)


# ---------------------------------------------------------------------------
# Manifest -> render plan
# ---------------------------------------------------------------------------

def build_render_plan(manifest: dict) -> tuple[list[dict], list[dict]]:
    """Validate a project manifest and turn it into an ordered list of
    renderable segment specs, plus a list of warnings for any order that
    had to be skipped.

    Each segment spec:
        {
          "order": int,
          "label": str | None,
          "pages": [
              {"image_path": Path, "duration_seconds": float},
              ...  # one entry per visual page, duration already split
          ],
          "audio_path": Path,
          "width": int,
          "height": int,
        }

    Raises VideoRenderError if the manifest has zero renderable orders, or
    if renderable orders don't share one common resolution (v1 requires
    uniform resolution across the whole project - see module docstring).
    """
    from common.project_store import order_dir

    project_id = manifest.get("project_id")
    orders = manifest.get("orders") or []
    if not orders:
        raise VideoRenderError(f"Project '{project_id}' has no orders in its manifest.")

    segments: list[dict] = []
    warnings: list[str] = []
    resolutions: set[tuple[int, int]] = set()

    for entry in sorted(orders, key=lambda o: o.get("order", 0)):
        order = entry.get("order")
        label = entry.get("label")
        audio = entry.get("audio")
        visual = entry.get("visual")

        missing = []
        if not audio or not audio.get("filename"):
            missing.append("audio")
        if not visual or not visual.get("filenames"):
            missing.append("visual")
        if missing:
            warnings.append(f"order {order} skipped: missing {' and '.join(missing)}")
            continue

        duration = audio.get("duration_seconds")
        if not duration or duration <= 0:
            warnings.append(
                f"order {order} skipped: audio has no usable duration_seconds"
            )
            continue

        width, height = visual.get("width"), visual.get("height")
        if not width or not height:
            warnings.append(f"order {order} skipped: visual has no width/height")
            continue
        resolutions.add((width, height))

        o_dir = order_dir(project_id, order)
        filenames = visual["filenames"]
        n_pages = len(filenames)
        # Pagination duration split: divide evenly - see module docstring
        # for why "evenly" is the documented v1 choice.
        per_page = duration / n_pages
        pages = [
            {"image_path": o_dir / fname, "duration_seconds": per_page}
            for fname in filenames
        ]

        segments.append(
            {
                "order": order,
                "label": label,
                "pages": pages,
                "audio_path": o_dir / audio["filename"],
                "duration_seconds": duration,
                "width": width,
                "height": height,
            }
        )

    if not segments:
        raise VideoRenderError(
            f"Project '{project_id}' has no renderable orders "
            f"(every order is missing audio and/or visual)."
        )

    if len(resolutions) > 1:
        readable = ", ".join(f"{w}x{h}" for w, h in sorted(resolutions))
        raise VideoRenderError(
            f"Project '{project_id}' mixes visual resolutions ({readable}). "
            f"video_renderer v1 requires every order to share one resolution."
        )

    for seg in segments:
        if not seg["audio_path"].exists():
            raise VideoRenderError(
                f"order {seg['order']}: audio file not found on disk: {seg['audio_path']}"
            )
        for page in seg["pages"]:
            if not page["image_path"].exists():
                raise VideoRenderError(
                    f"order {seg['order']}: visual file not found on disk: "
                    f"{page['image_path']}"
                )

    return segments, warnings


# ---------------------------------------------------------------------------
# Segment + concat rendering
# ---------------------------------------------------------------------------

def _render_segment(segment: dict, out_path: Path) -> None:
    """Render one order's segment: its visual page(s) held for the audio
    duration, with that order's audio.mp3 as the segment's audio track.

    Single-page orders use ffmpeg's `-loop 1` still-image-to-video path
    directly. Multi-page (paginated) orders first build a tiny concat-demuxer
    "page list" of image-hold sub-clips (silent), then mux the whole
    order's audio onto that combined visual track in a second pass - this
    keeps the image-timing logic (which supports arbitrary per-page
    durations) and the audio-muxing logic each simple and separately
    testable, rather than one large filter graph.

    Encode fps: `-r 2` is given as an *input* option on the looped image
    (before `-i`), not just an output option - since a still screenshot has
    no motion, there's nothing gained from encoding tens of near-identical
    frames per second, only wasted CPU/RAM. Measured impact on a ~1080p
    ~20s segment: dropped from ~14s wall time / ~1.1GB peak child RSS at a
    naive output-only `-r 30` down to ~1-3s / well under 150MB at input-side
    `-r 2` with `-preset ultrafast` - the difference between comfortably
    fitting a Render free-tier 512MB instance and reliably getting OOM-killed
    partway through a render (which surfaces to the caller as a bare
    connection failure, not a clean VideoRenderError, since the process
    dies before it can respond).
    """
    pages = segment["pages"]
    audio_path = segment["audio_path"]
    width, height = segment["width"], segment["height"]

    if len(pages) == 1:
        page = pages[0]
        _run_ffmpeg(
            [
                "-loop", "1", "-r", "2", "-i", str(page["image_path"]),
                "-i", str(audio_path),
                "-t", f"{page['duration_seconds']:.3f}",
                "-vf", f"scale={width}:{height},format=yuv420p",
                "-c:v", "libx264", "-preset", "ultrafast", "-r", "2",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                str(out_path),
            ],
            step=f"render order {segment['order']} (single page)",
        )
        return

    # Multi-page: render each page as a silent hold clip, concat them
    # visually, then lay the whole order's audio on top.
    with tempfile.TemporaryDirectory(prefix="render_pages_") as page_tmp:
        page_tmp_dir = Path(page_tmp)
        page_clips = []
        for idx, page in enumerate(pages, start=1):
            clip_path = page_tmp_dir / f"page_{idx:02d}.mp4"
            _run_ffmpeg(
                [
                    "-loop", "1", "-r", "2", "-i", str(page["image_path"]),
                    "-t", f"{page['duration_seconds']:.3f}",
                    "-vf", f"scale={width}:{height},format=yuv420p",
                    "-c:v", "libx264", "-preset", "ultrafast", "-r", "2", "-an",
                    str(clip_path),
                ],
                step=f"render order {segment['order']} page {idx}/{len(pages)}",
            )
            page_clips.append(clip_path)

        pages_concat_list = page_tmp_dir / "pages.txt"
        pages_concat_list.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in page_clips), encoding="utf-8"
        )
        silent_visual = page_tmp_dir / "visual_only.mp4"
        _run_ffmpeg(
            [
                "-f", "concat", "-safe", "0", "-i", str(pages_concat_list),
                "-c", "copy",
                str(silent_visual),
            ],
            step=f"concat pages for order {segment['order']}",
        )

        _run_ffmpeg(
            [
                "-i", str(silent_visual), "-i", str(audio_path),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                str(out_path),
            ],
            step=f"mux audio for order {segment['order']}",
        )


def _concat_cut(segment_paths: list[Path], out_path: Path) -> None:
    """Join pre-rendered segment .mp4s with a hard cut, via ffmpeg's
    concat demuxer (stream copy - no re-encode, no quality loss, and no
    risk of drift since every segment was already encoded at the same
    resolution/framerate)."""
    with tempfile.TemporaryDirectory(prefix="render_concat_") as tmp:
        list_path = Path(tmp) / "segments.txt"
        list_path.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in segment_paths), encoding="utf-8"
        )
        _run_ffmpeg(
            [
                "-f", "concat", "-safe", "0", "-i", str(list_path),
                "-c", "copy",
                str(out_path),
            ],
            step="concat all segments (cut)",
        )


def _concat_crossfade(
    segment_paths: list[Path], out_path: Path, crossfade_seconds: float
) -> None:
    """Join pre-rendered segments with xfade/acrossfade transitions.

    Requires a full re-encode (filter graphs can't stream-copy), and each
    transition overlaps two adjacent segments by crossfade_seconds, so the
    combined output is `sum(durations) - (n-1)*crossfade_seconds` long.
    Segment durations are re-probed here (rather than trusting the
    manifest) since ffmpeg's own encoded segment length is what the filter
    graph's offsets must line up with.
    """
    n = len(segment_paths)
    if n == 1:
        shutil.copyfile(segment_paths[0], out_path)
        return

    durations = [probe_duration_seconds(p) for p in segment_paths]
    if any(d is None for d in durations):
        raise VideoRenderError(
            "Could not determine segment durations for crossfade transitions "
            "(ffprobe unavailable or a segment file is unreadable)."
        )

    inputs: list[str] = []
    for p in segment_paths:
        inputs += ["-i", str(p)]

    # Chain xfade/acrossfade pairwise: [0][1] -> v1/a1, [v1][2] -> v2/a2, ...
    filter_parts = []
    v_label, a_label = "0:v", "0:a"
    offset = durations[0] - crossfade_seconds
    for i in range(1, n):
        next_v, next_a = f"{i}:v", f"{i}:a"
        out_v, out_a = f"v{i}", f"a{i}"
        filter_parts.append(
            f"[{v_label}][{next_v}]xfade=transition=fade:"
            f"duration={crossfade_seconds:.3f}:offset={offset:.3f}[{out_v}]"
        )
        filter_parts.append(
            f"[{a_label}][{next_a}]acrossfade=d={crossfade_seconds:.3f}[{out_a}]"
        )
        v_label, a_label = out_v, out_a
        if i + 1 < n:
            offset += durations[i] - crossfade_seconds

    filter_complex = ";".join(filter_parts)
    _run_ffmpeg(
        [
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{v_label}]", "-map", f"[{a_label}]",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ],
        step="concat all segments (crossfade)",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_project_video(
    manifest: dict,
    out_path: Path,
    transition: str = DEFAULT_TRANSITION,
    crossfade_seconds: float = CROSSFADE_SECONDS,
) -> dict:
    """Render a full project's manifest into a single MP4 at out_path.

    Returns:
        {
          "output_path": str,
          "total_duration_seconds": float,
          "orders": [{"order", "label", "duration_seconds", "status"}, ...],
          "warnings": [str, ...],
        }
    Raises VideoRenderError for bad/incomplete manifests, missing ffmpeg,
    or any failed ffmpeg step.
    """
    if transition not in TRANSITION_STYLES:
        raise VideoRenderError(
            f"Invalid transition '{transition}'. Choose one of: "
            f"{', '.join(TRANSITION_STYLES)}"
        )
    if not ffmpeg_available():
        raise VideoRenderError(
            f"ffmpeg is not available on this deployment (looked for "
            f"'{FFMPEG_BINARY}' on PATH). Install ffmpeg to use video_renderer."
        )

    segments, warnings = build_render_plan(manifest)

    tmp_dir = tempfile.mkdtemp(prefix="video_renderer_")
    try:
        tmp_dir_path = Path(tmp_dir)
        segment_paths = []
        for segment in segments:
            seg_path = tmp_dir_path / f"segment_{segment['order']:02d}.mp4"
            _render_segment(segment, seg_path)
            segment_paths.append(seg_path)

        if transition == "crossfade":
            _concat_crossfade(segment_paths, out_path, crossfade_seconds)
            total_duration = sum(s["duration_seconds"] for s in segments) - (
                (len(segments) - 1) * crossfade_seconds
            )
        else:
            _concat_cut(segment_paths, out_path)
            total_duration = sum(s["duration_seconds"] for s in segments)

        if not out_path.exists() or out_path.stat().st_size == 0:
            raise VideoRenderError("Render completed but output file is missing or empty.")

        return {
            "output_path": str(out_path),
            "total_duration_seconds": round(total_duration, 3),
            "transition": transition,
            "orders": [
                {
                    "order": s["order"],
                    "label": s["label"],
                    "duration_seconds": s["duration_seconds"],
                    "pages": len(s["pages"]),
                    "status": "rendered",
                }
                for s in segments
            ],
            "warnings": warnings,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)