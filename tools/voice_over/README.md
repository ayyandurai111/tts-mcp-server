# `voice_over`

Text-to-speech, via [`edge-tts`](https://github.com/rany2/edge-tts) (uses
Microsoft Edge's online neural voices — no API key needed, but requires
outbound network access to `speech.platform.bing.com`).

## Files

| File | Purpose |
|---|---|
| `core.py` | `generate_audio_core()` — the actual TTS call + duration lookup; `TTSGenerationError`; `list_available_voices()`. Pure function: plain args in, result dict out, raises on failure, never touches `sys.exit`. |
| `schema.py` | `build_tool()` — the MCP `Tool` object (name, description, `inputSchema`) exposed via `mcp_layer/registry.py`. |
| `handler.py` | `handle(arguments)` — MCP `call_tool` logic for this tool: validates input, calls `core.generate_audio_core`, optionally syncs into a project via `common.project_store.save_audio_for_order`, returns the standard `{"success": ...}` result. |
| `tests/test_tts_core.py` | Tests `core.py` with `edge_tts.Communicate`/`edge_tts.list_voices` mocked — no real network calls. |

## MCP tool contract

**Input** (`inputSchema` in `schema.py`):

| Field | Required | Default | Notes |
|---|---|---|---|
| `text` | yes | — | Text to convert to speech |
| `voice` | no | `common.config.DEFAULT_VOICE` | e.g. `en-IN-PrabhatNeural`, `en-US-GuyNeural` |
| `rate` | no | `DEFAULT_RATE` | e.g. `+10%`, `-20%` |
| `pitch` | no | `DEFAULT_PITCH` | e.g. `+10Hz`, `-5Hz` |
| `volume` | no | `DEFAULT_VOLUME` | e.g. `+10%`, `-20%` |
| `output_filename` | no | auto-generated | Custom filename |
| `project_id` | no | — | Groups this clip with a matching `visual_creator` screenshot (see below) |
| `order` | required if `project_id` set | — | Beat/step number; must match the corresponding `visual_creator` checklist entry's position |
| `label` | no | — | Only used with `project_id`; stored in the manifest for readability |

**Output**: `{"success": true, "content": "<original text>", "filename": "<name>.mp3", "duration_seconds": ..., "timestamp": "..."}` — no audio bytes or filesystem path. Fetch the file via `GET /api/v1/audio/{filename}` (see `api/routes/audio.py`).

## Project sync

If `project_id` (+ required `order`) is given, the generated MP3 is
additionally copied to
`{TEMP_DIR}/projects/{project_id}/order_{order:02d}/audio.mp3` and recorded
(with its duration) in that project's `manifest.json`, via
`common.project_store.save_audio_for_order`. This is how a `voice_over`
call and a `visual_creator` call for the same beat get matched up for
`video_renderer` to later stitch together — see
`tools/video_renderer/README.md`.

A sync failure (e.g. disk issue) does **not** fail the whole call — the
MP3 was already generated successfully, so the result includes a
`project_warning` field instead of an error.
