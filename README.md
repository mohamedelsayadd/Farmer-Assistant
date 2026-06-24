# ReNile Farmer Assistant

Arabic farm assistant backend for ReNile users. The service exposes a FastAPI chat endpoint, uses an OpenAI-compatible LLM API for conversation and tool calling, reads ReNile device data through backend tools, and stores short-term conversation memory in Redis.

The assistant is prompted to answer in simple Egyptian Arabic and can help with:

- Current farm/device readings.
- Historical daily or hourly readings for selected devices.
- General agricultural questions that do not require private farm data.
- Follow-up questions using recent Redis-backed conversation/tool context.

## Tech Stack

- Python 3.12
- FastAPI
- LangGraph-style agent orchestration
- OpenAI SDK against an OpenAI-compatible LLM server
- Redis for short-term memory
- HTTPX for ReNile API calls
- Streamlit manual testing client
- pytest test suite

## Project Structure

```text
.
|-- src/
|   |-- main.py                         # FastAPI application
|   |-- api/v1/endpoints/chat.py        # Chat endpoint
|   |-- agent/                          # Agent graph, prompt, and tool routing
|   |-- core/                           # Settings and logging
|   |-- memory/                         # Redis memory implementation
|   |-- models/schemas/                 # Pydantic request/response schemas
|   |-- providers/                      # LLM and ReNile API clients
|   `-- services/                       # Chat service and response processors
|-- tests/                              # Unit tests
|-- docker/compose.yaml                 # Redis for local development
|-- streamlit_app.py                    # Manual chat tester
|-- .env.example                        # Expected environment variables
`-- pyproject.toml                      # Dependencies and tooling
```

## Requirements

- Python `>=3.12,<3.13`
- `uv`
- Docker, for local Redis
- An OpenAI-compatible LLM endpoint, such as vLLM or another compatible server
- A valid ReNile JWT for testing authenticated device data flows

## Setup

Install dependencies:

```bash
uv sync
```

Create your local environment file:

```bash
cp .env.example .env
```

Update `.env` with your local values. Do not commit real secrets.

Important settings:

```env
LLM_API_KEY=EMPTY
LLM_BASE_URL=http://localhost:5000/v1
LLM_MODEL=Qwen/Qwen2.5-1.5B-Instruct
REDIS_URL=redis://localhost:6379/0
RENILE_API_BASE_URL=https://renile-iot.com
CHAT_API_BASE_URL=http://localhost:8000
```

## Running Locally

Start Redis:

```bash
docker compose -f docker/compose.yaml up -d redis
```

Start your OpenAI-compatible LLM server separately and make sure `LLM_BASE_URL` and `LLM_MODEL` match it.

Start the FastAPI app:

```bash
uv run uvicorn main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## API

### `POST /api/v1/chat`

Request body:

```json
{
  "jwt": "<renile-jwt>",
  "conversation_id": "conversation-123",
  "message": "آخر قراءات المزرعة إيه؟"
}
```

Response body:

```json
{
  "conversation_id": "conversation-123",
  "message": "..."
}
```

The JWT is required by the backend to call ReNile APIs. It is not exposed to the LLM tool schemas, prompts, memory, or logs.

## Manual Streamlit Tester

Run the Streamlit client:

```bash
uv run streamlit run streamlit_app.py
```

In the sidebar, provide:

- Backend URL, for example `http://localhost:8000`.
- ReNile JWT.
- Conversation ID, generated automatically unless changed manually.

## Agent Tools

The LLM can request backend-executed tools for farm data:

- `get_current_readings`: gets latest device readings from ReNile.
- `get_devices_ids`: discovers the user's available devices before historical queries.
- `get_last_duration_summary`: gets daily historical rows for a selected device and period.
- `get_specific_time_readings`: gets hourly readings for a selected device on a specific day/time.

Historical tools require a real `device_id` resolved from `get_devices_ids`. Device names are never passed directly as historical tool IDs.

## Memory Behavior

Redis stores recent conversation messages and internal tool context under a conversation key. Defaults from `.env.example`:

- TTL: `3600` seconds
- Max messages: `12`

Tool context is injected into later LLM calls as system context so follow-up questions can use recent data without exposing backend internals to the user.

## Development Commands

Run tests:

```bash
uv run pytest
```

Run a focused test file:

```bash
uv run pytest tests/test_tools.py
```

Syntax-check backend code:

```bash
uv run python -m compileall src
```

Syntax-check the Streamlit client:

```bash
uv run python -m py_compile streamlit_app.py
```

## Notes

- Settings are loaded from root `.env` using `pydantic-settings`.
- Redis must be reachable at API startup because the FastAPI lifespan pings Redis.
- ReNile API paths are configured through `RENILE_CURRENT_READINGS_PATH` and `RENILE_HISTORICAL_READINGS_PATH`.
- The assistant must answer in simple Egyptian Arabic according to `src/agent/prompts.py`.
