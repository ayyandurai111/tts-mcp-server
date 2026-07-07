# VoiceOver MCP Server

Server exposing **two MCP tools** over Streamable HTTP + legacy SSE, plus a
matching REST API:

- `voice_over` — text-to-speech.
- `visual_creator` — turns a checklist of code/command entries into VS
  Code-style code screenshots and terminal-style command screenshots (SVGs),
  for coding vlogs.

Generated files (MP3s and SVGs) are written to a temp directory (safe for
ephemeral disks on Render/Railway/Fly/etc.) and served back over HTTP so any
LLM client or frontend can fetch them.

## Project layout

```
app/
├── main.py              # FastAPI app factory: middleware, lifespan, routers
├── config.py             # all env-var configuration in one place
│
├── models/
│   └── schemas.py         # TTSRequest / TTSResponse Pydantic models
│
├── core/                    # transport-agnostic business logic
│   ├── tts.py                 # edge-tts wrapper (generate_audio_core, list_available_voices)
│   ├── visual.py                # visual_creator orchestration around vlogshot/
│   ├── vlogshot/                  # vendored screenshot-rendering package (see below)
│   ├── files.py                     # filename generation, temp-path resolution, cleanup
│   └── logging.py                     # in-memory request log
│
├── mcp/                              # MCP protocol layer
│   ├── server.py                       # Server("voiceover-mcp-server") instance
│   ├── tools.py                          # tool schemas: "voice_over" + "visual_creator"
│   └── handlers.py                         # call_tool dispatch -> core.tts / core.visual
│
├── routes/                                    # REST layer (one file per resource)
│   ├── root.py                                  # GET / , GET /health
│   ├── tts.py                                     # POST /api/v1/tts
│   ├── voices.py                                    # GET /api/v1/voices
│   ├── audio.py                                       # GET /api/v1/audio/{filename}
│   ├── visuals.py                                       # GET /api/v1/visual/{filename}
│   └── logs.py                                            # GET /api/v1/logs
│
└── utils/
    └── formatting.py                                        # file-size + timestamp helpers

tests/                                                            # pytest suite
run.py                                                              # entry point
```

`app/core/vlogshot/` is a vendored copy of the standalone
`vlog_screenshot_tool` CLI project — same rendering code (checklist parsing,
zip extraction, SVG rendering, themes, fonts), reused here as a library
instead of being invoked as a subprocess.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # edit as needed
python run.py
```

Server starts on `http://0.0.0.0:8080` by default. Docs at `/docs`.

## The `voice_over` MCP tool

Connect an MCP client to `GET /mcp/sse`. The single exposed tool:

- **Input**: `text` (required), `voice`, `rate`, `pitch`, `volume`, `output_filename`
- **Output**: `{ "success": true, "content": "<original text>", "filename": "<name>.mp3", "timestamp": "..." }`

The tool does **not** return audio bytes or a filesystem path — only the
filename. Fetch the actual file with:

```
GET /api/v1/audio/{filename}
```

This is what your deploy/render layer should call to play or download the
generated clip.

## The `visual_creator` MCP tool

Connect an MCP client to `/mcp` (Streamable HTTP) or `/mcp/sse` (legacy SSE).

- **Input**:
  - `checklist` (required) — array of entries, each one of:
    - a zip-lookup code entry: `{file, start_line, end_line, label}`
    - an inline code entry (no zip needed): `{path, start_line, code, label}`
    - a command entry (no zip needed): `{type: "command", command, output, label}`
  - `zip_base64` — base64-encoded project zip; required only if `checklist`
    has at least one zip-lookup code entry
  - `theme` (`dark` / `light` / `high-contrast`, default `dark`)
  - `style` (`vscode` / `minimal`, default `vscode`)
  - `font_size` (default `22`), `width` (default `1920`)
- **Output**: `{ "success": true, "results": [{order, label, status, detail}, ...], "files": ["<name>.svg", ...], "download_url_template": "/api/v1/visual/{filename}", "timestamp": "..." }`

One bad entry never fails the whole call — `results[i].status` is `OK`,
`CLIPPED`, or `SKIPPED (reason)` per entry, same as the underlying `vlogshot`
CLI. Fetch each generated SVG with:

```
GET /api/v1/visual/{filename}
```

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
| GET | `/api/v1/visual/{filename}` | Download a generated SVG screenshot |
| GET | `/api/v1/logs` | Recent request log (monitoring) |

## Storage model

- All audio and visuals are written to a single ephemeral temp directory
  (`TEMP_DIR`, defaults to the OS temp dir + `voiceover_mcp`); visuals go in
  a `visuals/` subfolder of it.
- Filenames are sanitized and resolved with `Path(...).name` only — no path
  traversal via `output_filename`, `visual_creator` checklist entries, or
  either download route.
- Each `visual_creator` call gets a short random filename prefix, so repeat
  calls (even with identical labels) never overwrite each other's output.
- `AUDIO_TTL_SECONDS` / `VISUAL_TTL_SECONDS` (default 1 hour each) control a
  startup cleanup sweep that deletes stale files.
- Because storage is ephemeral, files will not survive a server restart on
  most PaaS platforms — by design. Both download endpoints return a clear
  404 if a file has expired or the instance was recycled.

## Testing

```bash
python -m pytest tests/ -v
```

Covers: filename/path safety, TTS core logic (edge-tts mocked, no real
network calls), `visual_creator` core rendering logic (inline code, command,
and zip-lookup entries; bad-input errors), both MCP tool handlers, and all
REST routes.

## Environment variables

See `.env.example`. Key ones:

- `PORT`, `HOST` — server binding
- `TEMP_DIR` — override the shared audio/visuals temp directory
- `AUDIO_TTL_SECONDS`, `VISUAL_TTL_SECONDS` — cleanup age thresholds
- `DEFAULT_VOICE`, `DEFAULT_RATE`, `DEFAULT_PITCH`, `DEFAULT_VOLUME` — TTS defaults
