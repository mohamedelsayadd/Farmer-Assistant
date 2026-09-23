# Repository Instructions

## Commands
- Use `uv` for Python work; do not use `pip` directly. Install/sync with `uv sync`.
- Run all tests with `uv run pytest`; run focused tests with `uv run pytest tests/test_tools.py` or `uv run pytest tests/test_tools.py::test_name`.
- Syntax-check backend code with `uv run python -m compileall src`.
- Start local Redis with `docker compose -f docker/compose.yaml up -d redis`. This compose file does not start an LLM server.
- Start the FastAPI app from the repo root with `uv run uvicorn main:app --reload`; startup pings Redis DB 0 and DB 1.
- Start the manual tester with `uv run streamlit run streamlit_app.py` (Streamlit is a dev dependency). It only calls `POST /api/v1/chat` on the URL entered in the UI.
- No linter or formatter is configured.
- `src/` is an installed package (`[tool.setuptools.packages.find] where = ["src"]`), so imports are top-level (`from agent.agent import ...`), never `src.agent...`. pytest sets `pythonpath = ["src"]` and `asyncio_mode = "auto"`, so async tests need no marker.

## Runtime Setup
- Settings load from root `.env` via `pydantic-settings`; `.env.example` is the verified list of env names. Keep real secrets only in `.env`.
- `.env` is the single source of truth: `src/core/config.py` declares no in-code defaults, so every key in `.env.example` is required and a missing one fails validation at startup. Add a new setting to `.env` and `.env.example` in the same change as the `Settings` field.
- `get_settings()` is `lru_cache`d. Never read env vars directly outside `core/config.py`.
- Required external services for live API use: Redis, an OpenAI-compatible LLM endpoint from `LLM_BASE_URL`, ReNile API access/JWT, the plant-disease prediction API from `PLANT_DISEASE_API_BASE_URL`, and — for voice messages only — the FMS-Voice ASR service from `ASR_REMOTE_BASE_URL`. None of them is contacted at startup.
- The speech-to-text subsystem is named ASR throughout: package `src/providers/ASR/`, settings `asr_*`, env keys `ASR_*`, `app.state.asr`, and `asr_*` log events. Existing `.env` files must rename `STT_*` to `ASR_*` and add `ASR_DTYPE` and `ASR_MAX_NEW_TOKENS`, or startup fails validation.
- `ASR_PROVIDER` selects the provider: `fms_voice` (the remote FMS-Voice HTTP service, the deployed default), `cohere` (local `CohereLabs/cohere-transcribe-arabic-07-2026` weights via `transformers`), or `faster_whisper`. `ASR_LANGUAGE` is required for `cohere` and must be `ar` or `en` for `fms_voice`; both raise at construction when the value is wrong.
- The Cohere weights come from a gated Hugging Face repo, so a token with accepted conditions must be available (`HF_TOKEN` or `hf auth login`). This applies only to a local-only run (`ASR_PROVIDER=cohere`) and to `streamlit_app.py`'s ASR tab — never to the deployed `fms_voice` path.
- No ASR model is loaded at startup, or ever, in the API process. `create_asr_provider` only constructs an object and `FMSVoiceASRProvider` is a plain HTTP client of `ASR_REMOTE_BASE_URL` (contract in `ASR-API-Contract.md`). There is no fallback to a local model: when FMS-Voice is unreachable, times out, or returns any 5xx, the transcription raises `ASRError` and the endpoint answers 503.
- ASR error taxonomy: `ASRUnsupportedAudioError` (the service's 415) becomes a 422, and every other `ASRError` becomes a 503. Requests are never retried inside the provider.
- There is no TTS. Speech is input-only (ASR); every reply is text.

## Entrypoints
- FastAPI app: `src/main.py`; routes: `/health` and `POST /api/v1/chat`.
- `src/main.py`'s lifespan is the composition root: it builds every dependency once (Redis clients, Agents SDK chat model + `ModelSettings`, ReNile client, plant-disease client, ASR, Langfuse client with the OpenInference Agents instrumentor) and hangs them on `app.state`. Nothing constructs its own providers; the agent receives clients through its constructor.
- The chat endpoint takes a bare `Request`, not a typed body. `services/chat_request_processor.py` branches on content type and normalizes JSON and multipart into one `ChatRequest`.
- JSON request schema is `jwt`, `conversation_id`, `message`. Multipart accepts `message`, `audio_file`, and/or `image_file`; `audio_file` is mutually exclusive with the other two, and at least one input is required. `wav_file` is a deprecated alias of `audio_file` and is still accepted.
- `audio_file` may be any format ffmpeg can decode (wav, mp3, m4a, ogg, opus, webm, flac, amr). There is no filename or content-type check — the ASR backend decides, and an undecodable upload returns 422.
- `audio_file` is transcribed into `message` before anything else runs, so the rest of the pipeline only ever sees text plus an optional `UploadedImage`.
- An image sent with no text gets a synthetic English marker message (`IMAGE_UPLOAD_MESSAGE`); `agent/agent.py::build_messages` appends `IMAGE_ATTACHMENT_MARKER` when an image accompanies text. The prompt instructs the model to ignore bracketed markers when picking reply language.
- `image_file` must be `.jpeg/.jpg/.png/.webp` and within `PLANT_DISEASE_MAX_IMAGE_BYTES`; oversize uploads return 413, bad type or empty return 422.
- Response schema is `conversation_id`, `message`, plus optional `source`, `disease`. The endpoint sets `response_model_exclude_none=True`, so unused optional fields are absent from the payload.

## Agent And Tools
- The agent is an OpenAI Agents SDK `Agent` run by `Runner`. Do not hand-roll the tool-calling loop. `src/agent/agent.py` builds it once in `FarmerAssistantAgent.__init__`; `src/agent/tools.py` holds the plain tool functions, `TOOLS` (each wrapped with `function_tool(..., failure_error_function=_tool_failed)`), and `AgentContext`; `src/agent/prompts.py` holds the prompt. The model is `OpenAIChatCompletionsModel` (Chat Completions, not the Responses API).
- The agent runs **statelessly** per request: no SDK session. `run()` converts Redis history into `{role, content}` input items, appends the current user turn, and calls `Runner.run(..., context=AgentContext(...))`.
- The `Agent`'s `instructions` is a callable that rebuilds the system prompt with today's date per run. Qwen `…</think>` is stripped from `final_output`.
- Round limit: at most `MAX_TOOL_ROUNDS = 4` tool rounds (5 model calls). Enforced with `max_turns=MAX_TOOL_ROUNDS + 1`: if the 5th model call still requests tools, the SDK runs them and then raises `MaxTurnsExceeded`, and `run()` returns the fixed `FALLBACK_RESPONSE`. An empty final output also returns it.
- Tool errors: `ValueError`/`httpx.HTTPError`/`ModelBehaviorError` become the tool output `"Tool failed temporarily."` (`TOOL_FAILED_MESSAGE`) and the model continues; other exceptions (e.g. `RedisError`) are re-raised, wrapped by the SDK in `UserError` with the original as `__cause__`, and `ChatService` catches them as `AgentsException`.
- All tool calls the model emits in one turn are executed (the old first-call routing is gone).
- Per-request data (`jwt`, `conversation_id`, `image`) and the clients (`renile_client`, `tool_cache`, `plant_disease_client`) reach tools only through their `RunContextWrapper[AgentContext]` first parameter, which is hidden from tool schemas. JWT must never be exposed to LLM tool schemas, prompts, Redis memory, logs, or callback/trace payloads.
- Historical flows must call `get_devices_ids` before reading tools; historical tools require a real `device_id`.
- Device-ID resolution is the subtle part: the model routinely passes a device name or list ordinal instead of an `_id`. The historical tools fetch the device list (cache-first) and `resolve_device_id` maps the raw value by exact id → ordinal → case-folded name. If it cannot resolve, the tool returns the device list *as its result* so the model re-asks, rather than calling ReNile with a bad ID.
- `get_last_duration_summary` calls ReNile `/api/v1/data/` with backend-fixed `data_type=month` and returns daily rows.
- `get_specific_time_readings` calls the same endpoint with backend-fixed `data_type=day` and returns hourly rows.
- `get_devices_ids` calls `RENILE_DEVICES_PATH` and returns a bare array of `{_id, name}`; `get_current_readings` calls `RENILE_CURRENT_READINGS_PATH` and returns a `{project_name, generated_at, devices[]}` object. The backend returns both already cleaned, so they are passed to the agent unchanged — do not add client-side processing for them.
- Tools return `json.dumps(result, ensure_ascii=False)` strings.
- `plant_diseases_detection` takes no model-supplied arguments. The image comes from `AgentContext`; the tool raises `ValueError` (→ "Tool failed temporarily.") when no image is attached. It POSTs the image as multipart to `PLANT_DISEASE_PREDICT_PATH` and passes the prediction dict through unchanged.
- Plant-disease results bypass the Redis tool cache entirely; only ReNile tool results are cached.
- `chat_service.plant_disease_metadata` scans the run's tool outputs (`AgentResult.tool_outputs`, `ToolOutput(name, output)` paired by `call_id`) for a non-failed `plant_diseases_detection` result and lifts `source`/`disease` onto `ChatResponse`.
- Observability: `create_langfuse_client` calls `OpenAIAgentsInstrumentor().instrument()`, which replaces the SDK's default OpenAI trace exporter and sends agent/model/tool spans into Langfuse via OTel; `ChatService.chat` is the `@observe` root span. Do not call `set_tracing_disabled(True)` — it would silence the instrumentor too.

## Providers
- `providers/llm.py::create_chat_model` returns an `OpenAIChatCompletionsModel` over `AsyncOpenAI`; `create_model_settings` returns its `ModelSettings` (sampling settings, `extra_body` `top_k` and `chat_template_kwargs.enable_thinking`). ReNile and plant-disease are plain classes in `src/providers/`.
- ASR follows interface + factory + `providers/` (`src/providers/ASR/`). A new ASR backend goes in `providers/ASR/providers/` and is wired only in its `factory.py`. `fms_voice.py` opens an `httpx.AsyncClient` per call like `plant_disease_client.py`, so there is no client on `app.state` and nothing to tear down.

## Memory And Cache
- Two Redis databases, deliberately separate. DB 0 stores only `user` and `assistant` messages in `conversation:{conversation_id}`; defaults are TTL `3600` seconds and max `12` messages.
- Redis DB 1 stores processed tool results as `tool_cache:{conversation_id}:{tool_name}:{arguments_hash}`; default TTL in `.env.example` is `600` seconds.
- Tool results are never written into prompt memory — the model only sees them within the round that fetched them. Tool execution checks the Redis tool cache before calling ReNile.

## Prompt Rules To Preserve
- The reply language is decided **only** from the text the user typed in the current message. Fully English text gets an English reply; Arabic or mixed Arabic/English gets Egyptian Arabic. Bracketed system markers, tool results, and earlier turns never change it. An image with no text follows the user's most recent text message, defaulting to Egyptian Arabic.
- Arabic text returned by tools (disease names, messages) must be restated in English when the reply is English, never pasted verbatim.
- Core-agronomy questions (crops, soil, irrigation, fertilisation, pests, weeds, plant diseases, planting/harvest timing, greenhouses, post-harvest) are answered in full from general knowledge with **no** tool call, whether or not they concern the user's own farm. Tools are the only source of truth for this user's devices and readings. Livestock, machinery, market prices, and subsidies stay out of scope.
- Out-of-scope questions reply exactly — Arabic: `آسف، مقدرش أرد على سؤالك , أقدر بس أساعدك في المواضيع الزراعية وقراءات مزرعتك وأمراض النباتات.` English: `Sorry, I can't answer that. I can only help with agriculture, your farm readings, and plant diseases.`
- Do not answer or call tools for farm/device readings before `2026-01-01`; reply exactly — Arabic: `القراءات قبل 2026 غير متاحة.` English: `Readings from before 2026 are not available.`
- The capability-help answer and the missing-data replies are fixed strings in both languages; keep both variants in sync when editing either.
- Any request carrying an uploaded plant image must call `plant_diseases_detection` before answering, and the reply branches on `is_plant` / `is_healthy` / `disease`.
- `agent.py`'s `@dynamic_prompt` rebuilds the system prompt per model call with today's date appended, for relative dates like `امبارح`, `من يومين`, and `آخر أسبوع`.

## Test Update Map
- Tool schema changes: update `tests/test_tools.py` because it asserts no JWT, runtime, or backend-fixed `data_type` exposure.
- Agent orchestration, middleware, device resolution, or caching changes: update `tests/test_agent.py` (runs the real SDK `Runner` against a scripted fake `agents.Model`).
- Prompt/date/language/scope changes: update `tests/test_agent_memory_context.py`.
- Historical response processor changes (`src/services/historical_summary_processor.py`, now the only processor): update `tests/test_historical_summary_processor.py`.
- ASR provider or factory changes (`src/providers/ASR/`): update `tests/test_asr_factory.py`, and `tests/test_asr_fms_voice.py` for the remote provider. `BASE_ENV`/`build_settings` live in `tests/conftest.py` and build `Settings` from a literal dict so no local `.env` is needed. Remote-provider tests drive `httpx.MockTransport` through the `_build_client` seam and must never reach a live URL, download models, or touch a GPU.
- Request parsing, endpoint, or response-shape changes: update `tests/test_chat_endpoint.py` and `tests/test_chat_schema.py`.
- Tests must stay hermetic: fakes only, no live Redis, LLM, ReNile, or plant-disease APIs, and no model downloads or GPU use.
