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
docker compose -f docker/compose.yaml up -d redis
uv run uvicorn main:app --reload            # from repo root; pings Redis DB 0 and DB 1 on startup
uv run streamlit run streamlit_app.py        # manual tester UI (dev dep); calls the running API
```

No linter/formatter is configured. `src/` is an installed package (`[tool.setuptools] where=["src"]`), so imports are top-level (`from agent.agent import ...`), never `src.agent...`. pytest sets `pythonpath=["src"]` and `asyncio_mode=auto`, so async tests need no marker.

Tests must stay hermetic: fakes only, no live Redis/LLM/ReNile, no model downloads or GPU use.

## Architecture

**Request flow.** `POST /api/v1/chat` (`src/api/v1/endpoints/chat.py`) is a bare `Request` handler, not a typed body — `services/chat_request_processor.py` branches on content type and normalizes JSON *and* multipart into one `ChatRequest`. Multipart accepts `message`, `audio_file` (any ffmpeg-decodable format; `wav_file` is a deprecated alias), and/or `image_file`; the audio field is mutually exclusive with the other two. Audio is transcribed (`wav_processor`) into `message` before anything else runs, so the rest of the pipeline only ever sees text plus an optional `UploadedImage`. An image with no text gets a synthetic English marker message; the prompt explicitly instructs the model to ignore bracketed markers when picking reply language. There is no TTS: replies are always text.

**Composition root.** `src/main.py`'s lifespan builds every dependency once (Redis clients, Agents SDK chat model + `ModelSettings`, ReNile client, plant-disease client, ASR, Langfuse client with the OpenInference Agents instrumentor) and hangs them on `app.state`. Nothing constructs its own providers; the agent receives clients through its constructor. No ASR model is loaded at startup or ever held in this process: the deployed `fms_voice` provider is a plain HTTP client of the FMS-Voice service, so boot is fast and depends on no external service.

**Agent** (`src/agent/agent.py`) is an OpenAI Agents SDK `Agent`, built once and run statelessly per request with `Runner.run` (no session — Redis DB 0 stays the source of truth for history). Per-request data and clients go in via `context=AgentContext(...)` and reach tools through their `RunContextWrapper` first parameter, which the SDK keeps out of tool schemas. Callable `instructions` rebuild the system prompt with today's date so relative Arabic dates resolve. `max_turns=MAX_TOOL_ROUNDS + 1` (4 tool rounds); `MaxTurnsExceeded` returns the fixed Arabic `FALLBACK_RESPONSE`. Qwen `</think>` reasoning is stripped from the final output. Each tool's `failure_error_function` turns `ValueError`/`httpx.HTTPError`/`ModelBehaviorError` into a `"Tool failed temporarily."` tool output; anything else is re-raised, wrapped by the SDK in `UserError` (an `AgentsException`, which `ChatService` catches). Don't hand-roll the tool loop; use `Runner`. The model is `OpenAIChatCompletionsModel` (Chat Completions, since vLLM serves that), not the Responses API.

**Device-ID resolution** is the subtle part. The model routinely passes a device *name* or a list ordinal instead of an `_id`. The historical tools in `agent/tools.py` fetch (cache-first) the device list and `resolve_device_id` maps the raw value to a real `_id` by exact id → ordinal → case-folded name. If it can't resolve, the tool returns the device list *as its result* so the model re-asks, rather than calling ReNile with garbage.

**Two Redis databases, deliberately separate.** DB 0 (`memory/redis_memory.py`) holds only `user`/`assistant` turns under `conversation:{id}`; DB 1 (`memory/tool_cache.py`) holds tool results under `tool_cache:{conversation_id}:{tool}:{args_hash}`. Tool results are never written into prompt memory — the model only sees them within the round that fetched them.

**JWT isolation.** The JWT arrives in the request body and reaches ReNile calls only via `AgentContext` inside the tools. It must never reach a tool schema, prompt, memory, log line, or trace; `tests/test_tools.py` and `tests/test_agent.py` assert this, along with the fact that `data_type` (`month`/`day`) is fixed backend-side and not model-controlled.

**Response side-channel.** `chat_service.plant_disease_metadata` scans the run's tool outputs (`AgentResult.tool_outputs`, name paired to output by `call_id`) for the `plant_diseases_detection` result and lifts `source`/`disease` onto `ChatResponse`. The endpoint uses `response_model_exclude_none=True`, so unused optional fields disappear from the payload.

**Providers.** `providers/llm.py` returns an `OpenAIChatCompletionsModel` (`create_chat_model`) and its sampling `ModelSettings` (`create_model_settings`); ReNile/plant-disease are plain classes; ASR follows interface + factory + `providers/` (`ASR_PROVIDER` = `fms_voice` | `cohere` | `faster_whisper`). New ASR backends go in `providers/ASR/providers/` and are wired in its `factory.py` only. `fms_voice` is the deployed default and calls the remote service documented in `ASR-API-Contract.md`; the two local providers remain selectable for a local-only run and are what `streamlit_app.py` uses directly. There is no fallback between them — FMS-Voice being unavailable is a 503, and an undecodable upload (the service's 415, surfaced as `ASRUnsupportedAudioError`) is a 422.

**Config.** `core/config.py` declares every field with an explicit `alias` and **no defaults**, so a key missing from `.env` fails validation at startup. Adding a setting means touching the `Settings` field, `.env`, and `.env.example` in the same change. `get_settings()` is `lru_cache`d — never read env vars directly elsewhere.

## Behavior contracts baked into prompts

`src/agent/prompts.py` contains exact response strings (out-of-scope refusal, capability help, pre-2026 readings refusal) in both Arabic and English. Reply language is decided *only* from the user's own typed text in the current message. Changing any of these means updating `tests/test_agent_memory_context.py`.

Scope is split in two deliberately: **core agronomy** (crops, soil, irrigation, fertilisation, pests, weeds, plant diseases, planting/harvest timing, greenhouses, post-harvest) is answered from the model's own knowledge with no tool call, even when the question has nothing to do with the user's own farm; **this user's devices and readings** may come only from tools. The capability-help string advertises three things, matching that split plus image diagnosis. Anything outside agriculture — livestock, machinery, market prices, subsidies — still gets the fixed refusal.
