# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` holds the operational rules for this repo (runtime setup, prompt invariants, test update map). Read it as well — this file covers commands and the architecture that spans several modules.

## Commands

```bash
uv sync                                     # install/sync deps (never use pip)
uv run pytest                               # full suite
uv run pytest tests/test_tools.py           # one file
uv run pytest tests/test_tools.py::test_name  # one test
uv run python -m compileall src             # syntax-check backend
uv run python -m py_compile streamlit_app.py
docker compose -f docker/compose.yaml up -d redis
uv run uvicorn main:app --reload            # from repo root; pings Redis DB 0 and DB 1 on startup
uv run streamlit run streamlit_app.py       # manual tester
```

No linter/formatter is configured. `src/` is an installed package (`[tool.setuptools] where=["src"]`), so imports are top-level (`from agent.graph import ...`), never `src.agent...`. pytest sets `pythonpath=["src"]` and `asyncio_mode=auto`, so async tests need no marker.

Tests must stay hermetic: fakes only, no live Redis/LLM/ReNile, no model downloads or GPU use.

## Architecture

**Request flow.** `POST /api/v1/chat` (`src/api/v1/endpoints/chat.py`) is a bare `Request` handler, not a typed body — `services/chat_request_processor.py` branches on content type and normalizes JSON *and* multipart into one `ChatRequest`. Multipart accepts `message`, `wav_file`, and/or `image_file`; `wav_file` is mutually exclusive with the other two. Audio is transcribed (`wav_processor`) into `message` before anything else runs, so the rest of the pipeline only ever sees text plus an optional `UploadedImage`. An image with no text gets a synthetic English marker message; the prompt explicitly instructs the model to ignore bracketed markers when picking reply language. Voice replies are added *after* the agent returns, in `voice_response_processor.add_voice_response`, and TTS failure degrades to a text-only response.

**Composition root.** `src/main.py`'s lifespan builds every dependency once (Redis clients, LLM, ReNile client, plant-disease client, ASR, TTS) and hangs them on `app.state`. Nothing constructs its own providers; the agent receives clients through its constructor. ASR/TTS models load eagerly at startup, so app boot is slow and requires the model weights to be reachable.

**Agent loop** (`src/agent/graph.py`) is a hand-rolled LangGraph-style loop, not LangGraph. Each round: one LLM chat call with `OPENAI_TOOLS`, then `_tool_path()` routes on the *first* tool call's name to one of three "nodes" (`current_tools` / `historical_tools` / `plant_disease_tools`); tool calls whose names fall outside the selected node's allowed set are skipped, not executed. Bounded by `MAX_TOOL_ROUNDS = 4`; falling off the end returns a fixed Arabic fallback string. The system prompt is rebuilt per request with today's date appended so relative Arabic dates resolve.

**Device-ID resolution** is the subtle part. The model routinely passes a device *name* or a list ordinal instead of an `_id`. Before any historical tool runs, `_resolve_historical_arguments` fetches (cache-first) the device list and maps the raw value to a real `_id` by exact id → ordinal → case-folded name. If it can't resolve, it returns the device list *as the tool result* so the model re-asks, rather than calling ReNile with garbage.

**Two Redis databases, deliberately separate.** DB 0 (`memory/redis_memory.py`) holds only `user`/`assistant` turns under `conversation:{id}`; DB 1 (`memory/tool_cache.py`) holds tool results under `tool_cache:{conversation_id}:{tool}:{args_hash}`. Tool results are never written into prompt memory — the model only sees them within the round that fetched them.

**JWT isolation.** The JWT arrives in the request body and is injected into ReNile calls only inside `agent/tools.py::execute_tool`. It must never reach a tool schema, prompt, memory, or log line; `tests/test_tools.py` asserts this, along with the fact that `data_type` (`month`/`day`) is fixed backend-side and not model-controlled.

**Response side-channel.** `chat_service.plant_disease_metadata` scrapes the returned `ToolContext` list for the `plant_diseases_detection` result and lifts `source`/`disease` onto `ChatResponse`. The endpoint uses `response_model_exclude_none=True`, so unused optional fields disappear from the payload.

**Providers.** LLM/ReNile/plant-disease are plain classes; ASR and TTS follow interface + factory + `providers/` (`ASR_PROVIDER` = `cohere` | `faster_whisper`). New speech backends go in `providers/<ASR|TTS>/providers/` and are wired in that subpackage's `factory.py` only.

**Config.** `core/config.py` declares every field with an explicit `alias` and **no defaults**, so a key missing from `.env` fails validation at startup. Adding a setting means touching the `Settings` field, `.env`, and `.env.example` in the same change. `get_settings()` is `lru_cache`d — never read env vars directly elsewhere.

## Behavior contracts baked into prompts

`src/agent/prompts.py` contains exact response strings (out-of-scope refusal, capability help, pre-2026 readings refusal) in both Arabic and English. Reply language is decided *only* from the user's own typed text in the current message. Changing any of these means updating `tests/test_agent_memory_context.py`.
