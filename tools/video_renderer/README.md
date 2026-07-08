# `video_renderer`

Stitches a project's synced `voice_over` narration + `visual_creator`
screenshots into a single MP4, via `ffmpeg`.

## Files

| File | Purpose |
|---|---|
| `core.py` | `render_project_video()` — the whole pipeline: manifest → per-order segment clips → concat. `build_render_plan()`, `VideoRenderError`, `TRANSITION_STYLES`, `DEFAULT_TRANSITION`, `ffmpeg_available()`. Pure functions, subprocess calls to `ffmpeg`, no `sys.exit`. |
| `schema.py` | `build_tool()` — the MCP `Tool` object exposed via `mcp_layer/registry.py`. |
| `handler.py` | `handle(arguments)` — MCP `call_tool` logic: validates `project_id`, calls `core.render_project_video`, persists the output via `common.project_store.save_final_video`, returns the standard result. |
| `tests/test_render_core.py` | Manifest-to-segments logic, missing-audio/visual handling, pagination duration-splitting, and ffmpeg command construction (mocked `subprocess.run`) — plus real end-to-end renders (cut, crossfade, pagination) when ffmpeg is available in the test environment. |

## Prerequisites: how this project runs on `voice_over` + `visual_creator` output

`video_renderer` doesn't take audio/image bytes directly — it reads a
project's `manifest.json` (see `common/project_store.py`), which is built
up by prior `voice_over` and `visual_creator` calls sharing the same
`project_id`:

1. Call `voice_over` once per beat, each with the same `project_id` and an
   `order` (1, 2, 3, ...).
2. Call `visual_creator` **once**, with a checklist containing one entry
   per beat (in `order` position) and the same `project_id`.
3. Call `video_renderer` with just that `project_id`.

## MCP tool contract

**Input** (`inputSchema` in `schema.py`):

| Field | Required | Default | Notes |
|---|---|---|---|
| `project_id` | yes | — | Must have matching `voice_over`/`visual_creator` calls already made against it |
| `transition` | no | `cut` | `cut` (hard cut, lossless stream-copy concat) or `crossfade` (xfade/acrossfade, full re-encode) |
| `crossfade_seconds` | no | `0.5` | Only used when `transition="crossfade"` |

**Output**: `{"success": true, "filename": "final_output.mp4", "total_duration_seconds": ..., "transition": ..., "orders": [{order, label, duration_seconds, pages, status}, ...], "warnings": [...], "download_url": "/api/v1/project/{project_id}/video", "timestamp": "..."}`.

Fetch the rendered file via `GET /api/v1/project/{project_id}/video`
(route declared in `api/routes/projects.py` — ahead of the generic
`/{order}/{filename}` route, so it isn't shadowed).

## How rendering works

For each manifest order with **both** audio and visual present:
1. The order's visual image(s) are held on screen for the audio's
   duration, muxed with `audio.mp3` as the segment's audio track.
2. If `visual.filenames` has more than one entry (a long code snippet
   `visual_creator` paginated), that order's audio duration is split
   **evenly** across the pages — the manifest has no per-page
   content-length signal to weight by, so this is the documented v1
   choice.
3. All segments are concatenated in `order` sequence into the final MP4
   (H.264/AAC), at the manifest's `visual.width`/`visual.height`.

Orders missing audio or visual are **skipped with a warning**, not a hard
failure — the render still proceeds with whatever orders are complete.

**v1 requires every order to share one resolution.** Mismatched
resolutions raise `VideoRenderError` rather than silently
scaling/letterboxing, since `visual_creator` already renders a whole batch
onto one fixed canvas size — a mismatch signals a real inconsistency
worth surfacing, not something to paper over.

## ffmpeg provisioning

This service deploys on Render's **native Python runtime** (see
`render.yaml` — plain `pip install`, no Dockerfile/`apt-get` hook), so
there's no OS package manager available at build time. `ffmpeg` itself is
provisioned via the `imageio-ffmpeg` pip package (pinned in
`requirements.txt`), which ships a static, self-contained binary — no
Dockerfile needed. `common.config.FFMPEG_BINARY` resolves to that binary
automatically; set the `FFMPEG_BINARY` env var to point at a different
binary instead (e.g. a system `ffmpeg` in a Docker-based deployment).

`ffmpeg -i` (parsing stderr) is used for duration probing rather than a
separate `ffprobe` call, since `imageio-ffmpeg` only ships `ffmpeg`.

## Not yet implemented

- Background music mixing — documented as a future extension.
- Per-page duration weighting by actual content length (currently even
  split — see above).
