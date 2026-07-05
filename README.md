# VoiceOver MCP Server

Text-to-speech server exposing **one MCP tool** (`voice_over`) over SSE, plus
a matching REST API. Audio is generated to a temp directory (safe for
ephemeral disks on Render/Railway/Fly/etc.) and served back over HTTP so any
LLM client or frontend can render it.

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
│   ├── files.py                 # filename generation, temp-path resolution, cleanup
│   └── logging.py                 # in-memory request log
│
├── mcp/                              # MCP protocol layer
│   ├── server.py                       # Server("voiceover-mcp-server") instance
│   ├── tools.py                          # tool schema: single "voice_over" tool
│   └── handlers.py                         # call_tool dispatch -> core.tts
│
├── routes/                                    # REST layer (one file per resource)
│   ├── root.py                                  # GET / , GET /health
│   ├── mcp_sse.py                                 # GET /mcp/sse
│   ├── tts.py                                       # POST /api/v1/tts
│   ├── voices.py                                      # GET /api/v1/voices
│   ├── audio.py                                         # GET /api/v1/audio/{filename}
│   └── logs.py                                            # GET /api/v1/logs
│
└── utils/
    └── formatting.py                                        # file-size + timestamp helpers

tests/                                                            # pytest suite (27 tests)
run.py                                                              # entry point
```

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

## REST API (mirrors the MCP tool 1:1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service info |
| GET | `/health` | Health + temp dir status |
| GET | `/mcp/sse` | MCP SSE connection |
| POST | `/api/v1/tts` | Generate speech, returns filename + download URL |
| GET | `/api/v1/voices` | List/filter available edge-tts voices |
| GET | `/api/v1/audio/{filename}` | Download/stream a generated clip |
| GET | `/api/v1/logs` | Recent request log (monitoring) |

## Storage model

- All audio is written to a single ephemeral temp directory (`TEMP_DIR`,
  defaults to the OS temp dir + `voiceover_mcp`).
- Filenames are sanitized and resolved with `Path(...).name` only — no path
  traversal via `output_filename` or the download route.
- `AUDIO_TTL_SECONDS` (default 1 hour) controls a startup cleanup sweep that
  deletes stale files.
- Because storage is ephemeral, files will not survive a server restart on
  most PaaS platforms — by design. The download endpoint returns a clear 404
  if a file has expired or the instance was recycled.

## Testing

```bash
python -m pytest tests/ -v
```

27 tests covering: filename/path safety, TTS core logic (edge-tts mocked, no
real network calls), the MCP `voice_over` tool handler, and all REST routes.

## Environment variables

See `.env.example`. Key ones:

- `PORT`, `HOST` — server binding
- `TEMP_DIR` — override the audio temp directory
- `AUDIO_TTL_SECONDS` — cleanup age threshold
- `DEFAULT_VOICE`, `DEFAULT_RATE`, `DEFAULT_PITCH`, `DEFAULT_VOLUME` — TTS defaults
