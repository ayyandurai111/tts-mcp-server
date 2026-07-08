# `visual_creator`

Turns a checklist of code/command entries into VS Code-style code
screenshots and terminal-style command screenshots, for coding vlogs.
Rendering itself is vector-first (SVG), then optionally rasterized to a
fixed-canvas 4K PNG.

## Files

| File | Purpose |
|---|---|
| `core.py` | `generate_visuals_core()` — orchestrates checklist parsing, zip extraction (if needed), rendering, persistence, and project sync. `VisualCreatorError`; `OUTPUT_FORMATS`. |
| `schema.py` | `build_tool()` — the MCP `Tool` object exposed via `mcp_layer/registry.py`. |
| `handler.py` | `handle(arguments)` — MCP `call_tool` logic: validates `checklist`, calls `core.generate_visuals_core`, returns the standard result. |
| `rasterize.py` | Shells out to an SVG rasterizer to produce the 4K PNG output; `RasterizeError`. |
| `vlogshot/` | Vendored copy of the standalone `vlog_screenshot_tool` CLI — checklist parsing, zip extraction, SVG rendering, themes, fonts — reused here as a library. |
| `tests/test_visual_core.py` | Tests `core.py`: inline code entries, command entries, zip-lookup entries, bad-input errors, project sync, cleanup. |
| `tests/test_rasterize.py` | Tests the SVG→PNG rasterization path. |

## MCP tool contract

**Input** (`inputSchema` in `schema.py`):

| Field | Required | Default | Notes |
|---|---|---|---|
| `checklist` | yes | — | Array of entries, in order (see below) |
| `zip_base64` | only if a zip-lookup entry is present | — | Base64-encoded project zip |
| `theme` | no | `DEFAULT_THEME` | `dark` / `light` / `high-contrast` |
| `style` | no | `vscode` | `vscode` (full editor chrome) or `minimal` (header bar only) |
| `font_size` | no | `22` | Pixels |
| `width` | no | `1920` | Fixed output width |
| `height` | no | `1080` | Fixed output height — every screenshot is exactly this size regardless of code length, so a batch is video-ready with no size mismatches |
| `output_format` | no | `png` | `png` (rasterized, ≥4K long edge) / `svg` (raw vector) / `both` |
| `project_id` | no | — | Groups every entry's screenshot(s) with a matching `voice_over` clip |

**Checklist entry shapes** — each entry is one of:
1. Zip-lookup code entry: `{file, start_line, end_line, label}` — resolved against `zip_base64`.
2. Inline code entry: `{path, start_line, code, label}` — rendered directly, no zip needed.
3. Command entry: `{type: "command", command, output, label}` — rendered as a terminal window, no zip needed.

**Output**: `{"success": true, "results": [{order, label, status, detail}, ...], "files": ["<name>.png", ...], "download_url_template": "/api/v1/visual/{filename}", "timestamp": "..."}`. One bad entry never fails the whole call — `results[i].status` is `OK`, `CLIPPED`, or `SKIPPED (reason)` per entry. Fetch each file via `GET /api/v1/visual/{filename}`.

Long code snippets that don't fit at the chosen font size are automatically
split into multiple same-sized screenshots (e.g. `visual_p1.png`,
`visual_p2.png`) rather than shrunk or cut off — `video_renderer` reads
this pagination directly from the manifest.

## Project sync

Each checklist entry's own position in the array is its `order` (1-indexed
— the first entry is order 1, etc.). If `project_id` is given, that
entry's rendered file(s) are additionally copied to
`{TEMP_DIR}/projects/{project_id}/order_{entry.order:02d}/visual.<ext>`
(or `visual_p1.<ext>`, `visual_p2.<ext>`, ... if paginated) and recorded in
the project's `manifest.json`, via `common.project_store.save_visual_for_order`.

**Important**: because `order` is derived from array position, submit all
of a project's checklist entries in **one** `visual_creator` call (in the
order you want them numbered) rather than multiple single-item calls —
otherwise every call's first entry lands on `order=1` and overwrites the
previous one. See `tools/video_renderer/README.md` for the full sync
workflow.
