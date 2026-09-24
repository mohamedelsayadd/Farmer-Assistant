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

**Request flow.** `POST /api/v1/chat` (`src/api/v1/endpoints/chat.py`) is a bare `Request` handler, not a typed body — `services/chat_request_processor.py` branches on content type and normalizes JSON *and* multipart into one `ChatRequest`. Multipart accepts `message`, `audio_file` (any ffmpeg-decodable format; `wav_file` is a deprecated alias), and/or `image_file`; the audio field is mutually exclusive with the other two. Audio is transcribed (`read_audio_file`) into `message` before anything else runs, so the rest of the pipeline only ever sees text plus an optional `UploadedImage`. An image with no text gets a synthetic English marker message; the prompt explicitly instructs the model to ignore bracketed markers when picking reply language. There is no TTS: replies are always text.

**Composition root.** `src/main.py`'s lifespan builds every dependency once (Redis clients, ReNile client, plant-disease client, ASR, Langfuse client with the OpenInference Agents instrumentor — only when `LANGFUSE_OBSERVE=true` and keys are set; otherwise the client is built with `tracing_enabled=False` and Agents SDK tracing is disabled via `set_tracing_disabled(True)`) and hangs them on `app.state`; `ChatService` receives the clients through its constructor. The LLM is the exception: `agent/agent.py` builds its model and `farmer_agent` at import time from `get_settings()`, like the SDK guide. No ASR model is loaded at startup or ever held in this process: the deployed `fms_voice` provider is a plain HTTP client of the FMS-Voice service, so boot is fast and depends on no external service.

**Agent** (`src/agent/agent.py`) is a module-level `farmer_agent = Agent(...)` with its own `OpenAIChatCompletionsModel` and `ModelSettings`, defined in the same file (no separate LLM provider module). `ChatService` (the "manager", like the guide's `ResearchManager`) runs it statelessly per request with `Runner.run` (no session — Redis DB 0 stays the source of truth for history), starting at `starting_agent(history)`. Tests swap the model via `ChatService(run_config=RunConfig(model=FakeModel))`. Per-request data and clients go in via `context=AgentContext(...)` and reach tools through their `RunContextWrapper` first parameter, which the SDK keeps out of tool schemas. Callable `instructions` rebuild the system prompt with today's date so relative Arabic dates resolve. `max_turns=MAX_TOOL_ROUNDS + 1` (4 tool rounds); `MaxTurnsExceeded` returns the fixed Arabic `FALLBACK_RESPONSE`. Qwen `</think>` reasoning is stripped from the final output. Each tool is decorated `@function_tool(failure_error_function=tool_failed)` with a docstring `Args:` block, and turns `ValueError`/`httpx.HTTPError`/`ModelBehaviorError` into a `"Tool failed temporarily."` tool output; anything else is re-raised, wrapped by the SDK in `UserError` (an `AgentsException`, which `ChatService` catches). Don't hand-roll the tool loop; use `Runner`. The model is `OpenAIChatCompletionsModel` (Chat Completions, since vLLM serves that), not the Responses API.

**Customer support handoff.** `support_agent` (same file, same model) is a `handoffs=[support_agent]` target of `farmer_agent` — never `as_tool` — and hands back via `support_agent.handoffs = [farmer_agent]` (assigned after both exist). Its only tool is `get_devices_status`, whose `ReNileClient` method returns dummy data until the backend API exists. Each assistant turn in Redis DB 0 carries the name of the agent that wrote it (`result.last_agent.name`), and `starting_agent(history)` starts the next run at that agent (farmer when untagged), so support follow-ups like "أيوه" never depend on the farmer re-detecting them. The farmer hands off only on an explicit user-reported device/sensor/connectivity/package/account problem (or, for untagged history, a reply continuing a support conversation) — never because a tool result looks stale; support hands back anything outside its flow. The two prompts live in separate files: `agent/prompts.py` (Farmer Assistant, incl. handoff rules) and `agent/support_prompts.py` (`SUPPORT_PROMPT`, a strict sequential flow: identify device → sensor problem (verify, then support will contact) or device problem → WIFI credentials check / 4G manual renewal check (expired → recharge, stop) → power + indicator check → support will contact).

**Device-ID resolution** is the subtle part. The model routinely passes a device *name* or a list ordinal instead of an `_id`. The historical tools in `agent/tools.py` fetch (cache-first) the device list and `resolve_device_id` maps the raw value to a real `_id` by exact id → ordinal → case-folded name. If it can't resolve, the tool returns the device list *as its result* so the model re-asks, rather than calling ReNile with garbage.

**Two Redis databases, deliberately separate.** DB 0 (`memory/redis_memory.py`) holds only `user`/`assistant` turns under `conversation:{id}` (assistant turns also store the answering agent's name, which `build_messages` never passes to the model); DB 1 (`memory/tool_cache.py`) holds tool results under `tool_cache:{conversation_id}:{tool}:{args_hash}`. Tool results are never written into prompt memory — the model only sees them within the round that fetched them.

**JWT isolation.** The JWT arrives in the request body and reaches ReNile calls only via `AgentContext` inside the tools. It must never reach a tool schema, prompt, memory, log line, or trace; `tests/test_tools.py` and `tests/test_agent.py` assert this, along with the fact that `data_type` (`month`/`day`) is fixed backend-side and not model-controlled.

**Response side-channel.** `plant_diseases_detection` stores its prediction on `AgentContext.plant_prediction`; after the run `chat_service.plant_disease_metadata` lifts `source`/`disease` from it onto `ChatResponse`. The endpoint uses `response_model_exclude_none=True`, so unused optional fields disappear from the payload.

**Providers.** ReNile/plant-disease are plain classes (one method per tool — never merge tools or their client methods); ASR follows interface + factory + `providers/`, and `fms_voice` (`ASR_PROVIDER=fms_voice`) is the only provider: it calls the remote service documented in `ASR-API-Contract.md`. A new ASR backend would go in `providers/ASR/providers/` and be wired in `factory.py` only. FMS-Voice being unavailable is a 503, and an undecodable upload (the service's 415, surfaced as `ASRUnsupportedAudioError`) is a 422.

**Config.** `core/config.py` declares every field with an explicit `alias` and **no defaults**, so a key missing from `.env` fails validation at startup. Adding a setting means touching the `Settings` field, `.env`, and `.env.example` in the same change. `get_settings()` is `lru_cache`d — never read env vars directly elsewhere.

## Behavior contracts baked into prompts

`src/agent/prompts.py` contains exact response strings (out-of-scope refusal, capability help, pre-2026 readings refusal) in both Arabic and English. Reply language is decided *only* from the user's own typed text in the current message. Changing any of these means updating `tests/test_agent_memory_context.py`.

Scope is split in two deliberately: **core agronomy** (crops, soil, irrigation, fertilisation, pests, weeds, plant diseases, planting/harvest timing, greenhouses, post-harvest) is answered from the model's own knowledge with no tool call, even when the question has nothing to do with the user's own farm; **this user's devices and readings** may come only from tools. The capability-help string advertises three things, matching that split plus image diagnosis. Anything outside agriculture — livestock, machinery, market prices, subsidies — still gets the fixed refusal.
