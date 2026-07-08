# VoiceOver MCP Server

Server exposing **three MCP tools** over Streamable HTTP + legacy SSE, plus a
matching REST API:

- `voice_over` — text-to-speech.
- `visual_creator` — turns a checklist of code/command entries into VS
  Code-style code screenshots and terminal-style command screenshots
  (PNG/SVG), for coding vlogs.
- `video_renderer` — stitches a project's synced `voice_over` narration +
  `visual_creator` screenshots into a single MP4, via ffmpeg.

Generated files (MP3s, images, MP4s) are written to a temp directory (safe
for ephemeral disks on Render/Railway/Fly/etc.) and served back over HTTP so
any LLM client or frontend can fetch them.

## Project layout

The codebase is organized **one directory per tool**, so each tool's core
logic, MCP schema, MCP handler, and tests live together — adding a fourth
tool means adding one new directory under `tools/`, not touching four
scattered files.

```
common/                        # shared across all tools
├── config.py                    # all env-var configuration in one place
├── files.py                       # filename generation, temp-path resolution, cleanup
├── logging.py                       # in-memory request log
├── formatting.py                      # file-size + timestamp helpers
└── project_store.py                     # manifest/order sync layer (shared by all 3 tools)

tools/                          # one self-contained directory per MCP tool
├── voice_over/
│   ├── core.py                    # generate_audio_core, TTSGenerationError (edge-tts wrapper)
│   ├── schema.py                    # MCP Tool() inputSchema definition
│   ├── handler.py                     # MCP call_tool logic for this tool
│   └── tests/
│       └── test_tts_core.py
│
├── visual_creator/
│   ├── core.py                    # generate_visuals_core, VisualCreatorError
│   ├── schema.py
│   ├── handler.py
│   ├── rasterize.py                 # SVG -> PNG rasterizer
│   ├── vlogshot/                      # vendored screenshot-rendering package (see below)
│   └── tests/
│       ├── test_visual_core.py
│       └── test_rasterize.py
│
└── video_renderer/
    ├── core.py                    # render_project_video, VideoRenderError (ffmpeg pipeline)
    ├── schema.py
    ├── handler.py
    └── tests/
        └── test_render_core.py

mcp_layer/                      # MCP protocol/transport only — no tool-specific logic
├── server.py                     # Server("voiceover-mcp-server") instance
├── registry.py                     # aggregates each tool's schema.py + handler.py
├── errors.py                         # shared {"success": false, "error": ...} helper
├── sse_asgi.py                         # legacy SSE transport
├── streamable_http_asgi.py               # Streamable HTTP transport
└── tests/
    ├── test_mcp_handlers.py
    └── test_mcp_transport.py

api/                             # REST layer only — imports from tools/*/core.py directly
├── app.py                         # FastAPI app factory: middleware, lifespan, routers
├── models.py                        # TTSRequest / TTSResponse Pydantic models
├── routes/                            # one file per resource
│   ├── root.py                          # GET / , GET /health
│   ├── tts.py                             # POST /api/v1/tts
│   ├── voices.py                            # GET /api/v1/voices
│   ├── audio.py                               # GET /api/v1/audio/{filename}
│   ├── visuals.py                               # GET /api/v1/visual/{filename}
│   ├── projects.py                                # GET /api/v1/project(s), .../video
│   └── logs.py                                      # GET /api/v1/logs
└── tests/
    ├── test_routes_misc.py
    ├── test_routes_tts.py
    └── test_routes_projects.py

tests/                           # cross-cutting tests only (shared fixtures, project_store)
├── test_files.py
├── test_formatting.py
└── test_project_store.py

conftest.py                      # project-root pytest fixtures (e.g. `client`), shared by every test dir above
run.py                           # entry point
```

`tools/visual_creator/vlogshot/` is a vendored copy of the standalone
`vlog_screenshot_tool` CLI project — same rendering code (checklist parsing,
zip extraction, SVG rendering, themes, fonts), reused here as a library
instead of being invoked as a subprocess.

See each tool's own README for details specific to that tool:
[`tools/voice_over/README.md`](tools/voice_over/README.md) ·
[`tools/visual_creator/README.md`](tools/visual_creator/README.md) ·
[`tools/video_renderer/README.md`](tools/video_renderer/README.md)

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # edit as needed
python run.py
```

Server starts on `http://0.0.0.0:8080` by default. Docs at `/docs`.

## MCP tools

Connect an MCP client to `/mcp` (Streamable HTTP) or `/mcp/sse` (legacy
SSE). All three tools below are exposed on the same server; each is
documented in full in its own `tools/{name}/README.md`.

### `voice_over`

- **Input**: `text` (required), `voice`, `rate`, `pitch`, `volume`,
  `output_filename`, and optionally `project_id` + `order` + `label` to
  group this clip with a matching `visual_creator` screenshot for later
  sync.
- **Output**: `{ "success": true, "content": "<original text>", "filename": "<name>.mp3", "timestamp": "..." }`

The tool does **not** return audio bytes or a filesystem path — only the
filename. Fetch the actual file with `GET /api/v1/audio/{filename}`.

### `visual_creator`

- **Input**:
  - `checklist` (required) — array of entries, each one of:
    - a zip-lookup code entry: `{file, start_line, end_line, label}`
    - an inline code entry (no zip needed): `{path, start_line, code, label}`
    - a command entry (no zip needed): `{type: "command", command, output, label}`
  - `zip_base64` — base64-encoded project zip; required only if `checklist`
    has at least one zip-lookup code entry
  - `theme` (`dark` / `light` / `high-contrast`, default `dark`)
  - `style` (`vscode` / `minimal`, default `vscode`)
  - `font_size` (default `22`), `width` (default `1920`), `height` (default `1080`)
  - `output_format` (`png` / `svg` / `both`, default `png`)
  - optionally `project_id` (matched to `voice_over` calls by each
    checklist entry's own `order`)
- **Output**: `{ "success": true, "results": [{order, label, status, detail}, ...], "files": ["<name>.png", ...], "download_url_template": "/api/v1/visual/{filename}", "timestamp": "..." }`

One bad entry never fails the whole call — `results[i].status` is `OK`,
`CLIPPED`, or `SKIPPED (reason)` per entry. Fetch each generated file with
`GET /api/v1/visual/{filename}`.

### `video_renderer`

- **Input**: `project_id` (required — must have matching `voice_over` +
  `visual_creator` calls already made against it), `transition` (`cut`
  default / `crossfade`), `crossfade_seconds` (default `0.5`).
- **Output**: `{ "success": true, "filename": "final_output.mp4", "total_duration_seconds": ..., "orders": [...], "warnings": [...], "download_url": "/api/v1/project/{project_id}/video", "timestamp": "..." }`

Reads the project's manifest (written by `voice_over`/`visual_creator`),
holds each order's screenshot(s) on screen for that order's narration
duration, and concatenates every order into one MP4. Orders missing either
audio or visual are skipped with a warning, not a hard failure. Fetch the
result with `GET /api/v1/project/{project_id}/video`.

## REST API (mirrors the MCP tools 1:1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service info |
| GET | `/health` | Health + temp dir status |
| GET/POST/DELETE | `/mcp` | MCP Streamable HTTP transport |
| GET | `/mcp/sse` | MCP legacy SSE transport |
| POST | `/api/v1/tts` | Generate speech, returns filename + download URL |
| GET | `/api/v1/voices` | List/filter available edge-tts voices |
| GET | `/api/v1/audio/{filename}` | Download/stream a generated clip |
| GET | `/api/v1/visual/{filename}` | Download a generated screenshot |
| GET | `/api/v1/projects` | List known project_ids |
| GET | `/api/v1/project/{project_id}` | Get a project's manifest |
| GET | `/api/v1/project/{project_id}/{order}/{filename}` | Download one order's audio/visual file |
| GET | `/api/v1/project/{project_id}/video` | Download the rendered MP4 (`video_renderer` output) |
| GET | `/api/v1/logs` | Recent request log (monitoring) |

## Storage model

- All audio, visuals, and rendered videos are written to a single ephemeral
  temp directory (`TEMP_DIR`, defaults to the OS temp dir +
  `voiceover_mcp`); visuals go in a `visuals/` subfolder, project-synced
  files (including `video_renderer`'s output) go under a `projects/`
  subfolder.
- Filenames are sanitized and resolved with `Path(...).name` only — no path
  traversal via `output_filename`, checklist entries, or any download
  route.
- Each `visual_creator` call gets a short random filename prefix, so repeat
  calls (even with identical labels) never overwrite each other's output.
- `AUDIO_TTL_SECONDS` / `VISUAL_TTL_SECONDS` / project TTL (see
  `common/config.py`) control a startup cleanup sweep that deletes stale
  files.
- Because storage is ephemeral, files will not survive a server restart on
  most PaaS platforms — by design. Download endpoints return a clear 404 if
  a file has expired or the instance was recycled.

## Testing

```bash
python -m pytest -v
```

`pyproject.toml`'s `testpaths` covers `tests/`, `tools/`, `mcp_layer/`, and
`api/`, so this one command discovers every test across the whole tree —
each tool's own tests, the MCP dispatch tests, the REST route tests, and
the shared/cross-cutting tests all run together. Currently 102 tests.

Covers: filename/path safety, TTS core logic (edge-tts mocked, no real
network calls), `visual_creator` core rendering logic (inline code,
command, and zip-lookup entries; bad-input errors), `video_renderer`'s
manifest-to-segments logic and ffmpeg pipeline (mocked subprocess calls
plus real end-to-end renders when ffmpeg is available), all three MCP tool
handlers, and all REST routes.

## Environment variables

See `.env.example`. Key ones:

- `PORT`, `HOST` — server binding
- `TEMP_DIR` — override the shared audio/visuals/projects temp directory
- `AUDIO_TTL_SECONDS`, `VISUAL_TTL_SECONDS` — cleanup age thresholds
- `DEFAULT_VOICE`, `DEFAULT_RATE`, `DEFAULT_PITCH`, `DEFAULT_VOLUME` — TTS defaults
- `FFMPEG_BINARY` — override the ffmpeg binary `video_renderer` shells out
  to (defaults to the static binary bundled by `imageio-ffmpeg`, since this
  deploys on Render's Dockerfile-less native Python runtime)
- `DEFAULT_TRANSITION`, `CROSSFADE_SECONDS`, `RENDER_TIMEOUT_SECONDS` —
  `video_renderer` defaults
