<p align="center">
  <img src="farmer-assistant-banner.jpeg" alt="ReNile Farmer Assistant" width="100%">
</p>

# ReNile Farmer Assistant

Arabic-first AI agent for the [ReNile-IoT](https://renile-iot.com) platform, answering farmers' questions in Egyptian Arabic or English via text, voice, or plant photos.

Built on FastAPI, the agent calls backend tools to read live and historical ReNile device data, diagnoses plant diseases from images, and accepts voice questions (speech-to-text).

## Features

- 🌱 **Plant disease diagnosis** — send a leaf photo, get the likely disease and advice.
- 📊 **Farm readings** — current device status, plus daily summaries and hourly history.
- 🎙️ **Voice questions** — send an audio note in any common format (wav, mp3, m4a, ogg, opus, webm, flac, amr); it is transcribed and answered in text.
- 🧠 **Conversation memory** — Redis-backed follow-ups, with a separate cache for tool results.
- 🌍 **Bilingual** — replies in Egyptian Arabic or English, matching how the user wrote.

## Stack

Python 3.12 · FastAPI · OpenAI Agents SDK · OpenAI-compatible LLM · Redis · HTTPX · FMS-Voice ASR service (Cohere Transcribe Arabic) · Langfuse · pytest

## Quick Start

**Requirements:** Python `>=3.12,<3.13`, [`uv`](https://docs.astral.sh/uv/), Docker, an OpenAI-compatible LLM endpoint, and a ReNile JWT.

```bash
uv sync                                        # install dependencies
cp .env.example .env                           # then fill in your values
docker compose -f docker/compose.yaml up -d redis
uv run uvicorn main:app --reload               # http://localhost:8000
```

Check it's alive:

```bash
curl http://localhost:8000/health   # {"status":"ok"}
```

Then try it in the browser with the manual tester (text, plant image, or recorded voice). Enter the API URL and your ReNile JWT at the top:

```bash
uv run streamlit run streamlit_app.py  # http://localhost:8501
```

> **Note:** nothing is loaded at startup and no external service has to be up for the app to boot. Voice messages are transcribed by the FMS-Voice service at `ASR_REMOTE_BASE_URL` (see `ASR-API-Contract.md`); while it is down, voice requests return 503 and everything else keeps working.

## API

One endpoint: `POST /api/v1/chat`. Full reference in [Farmer-Assistant-API-Doc.md](Farmer-Assistant-API-Doc.md).

**Text** — `application/json`:

```json
{
  "jwt": "<renile-jwt>",
  "conversation_id": "conversation-123",
  "message": "آخر قراءات المزرعة إيه؟"
}
```

**Voice or image** — `multipart/form-data` with `jwt`, `conversation_id`, and one of:

| Field | Notes |
| --- | --- |
| `message` | Plain text. |
| `audio_file` | Audio in any ffmpeg-decodable format, transcribed then answered. Cannot be combined with the others. `wav_file` is a deprecated alias. |
| `image_file` | `.jpg` / `.jpeg` / `.png` / `.webp`, optionally alongside `message`. |

**Response:**

```json
{
  "conversation_id": "conversation-123",
  "message": "...",
  "disease": "...",
  "source": "..."
}
```

`disease` and `source` appear only for image diagnoses. Replies are always text, including for voice requests.

The JWT is used by the backend to call ReNile APIs. It is never exposed to the LLM, prompts, memory, or logs.

## Configuration

All settings come from `.env` — see [`.env.example`](.env.example) for the full annotated list. Every key is required; a missing one fails at startup rather than silently defaulting.

The ones you'll usually change:

| Key | Purpose |
| --- | --- |
| `LLM_BASE_URL`, `LLM_MODEL` | Your OpenAI-compatible LLM server. |
| `REDIS_URL`, `REDIS_TOOL_CACHE_URL` | Conversation memory (DB 0) and tool cache (DB 1). |
| `RENILE_API_BASE_URL` | ReNile platform API. |
| `PLANT_DISEASE_API_BASE_URL` | Plant disease prediction service. |
| `ASR_PROVIDER` | `fms_voice` (the remote FMS-Voice service; the only provider). |
| `ASR_REMOTE_BASE_URL` | The FMS-Voice service, e.g. `http://127.0.0.1:5001`. |
| `ASR_REMOTE_TIMEOUT_SECONDS` | Read timeout for a transcription request. |

## How It Works

```
request ──▶ parse (JSON / audio / image) ──▶ Agents SDK Runner ──▶ response
                                               │
                                               ├─ current readings  ──┐
                                               ├─ historical data   ──┼─▶ ReNile API
                                               ├─ device lookup     ──┘
                                               └─ plant diagnosis   ───▶ Disease API
```

The agent is an OpenAI Agents SDK `Agent` run by `Runner`, with a bounded tool-calling loop (at most 4 tool rounds). Historical questions always resolve a real device ID first, and tool results are cached in Redis so repeat questions don't re-hit ReNile. Readings before 2026-01-01 are out of range, and off-topic questions are declined.

## Development

```bash
uv run pytest                                  # all tests
uv run pytest tests/test_tools.py::test_name   # one test
uv run python -m compileall src                # syntax check
```

Tests use fakes throughout — no live Redis, LLM, or external APIs needed.

Project layout, architecture notes, and the rules to follow when changing the agent live in [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md).
