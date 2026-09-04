# Repository Instructions

## Commands
- Use `uv` for Python work; do not use `pip` directly. Install/sync with `uv sync`.
- Run all tests with `uv run pytest`; run focused tests with `uv run pytest tests/test_tools.py` or `uv run pytest tests/test_tools.py::test_name`.
- Syntax-check backend code with `uv run python -m compileall src`; syntax-check the Streamlit client with `uv run python -m py_compile streamlit_app.py`.
- Start local Redis with `docker compose -f docker/compose.yaml up -d redis`. This compose file does not start an LLM server.
- Start the FastAPI app from the repo root with `uv run uvicorn main:app --reload`; startup pings Redis DB 0 and DB 1.
- Start the manual tester with `uv run streamlit run streamlit_app.py`.
- No linter or formatter is configured.
- `src/` is an installed package (`[tool.setuptools.packages.find] where = ["src"]`), so imports are top-level (`from agent.graph import ...`), never `src.agent...`. pytest sets `pythonpath = ["src"]` and `asyncio_mode = "auto"`, so async tests need no marker.

## Runtime Setup
- Settings load from root `.env` via `pydantic-settings`; `.env.example` is the verified list of env names. Keep real secrets only in `.env`.
- `.env` is the single source of truth: `src/core/config.py` declares no in-code defaults, so every key in `.env.example` is required and a missing one fails validation at startup. Add a new setting to `.env` and `.env.example` in the same change as the `Settings` field.
- `get_settings()` is `lru_cache`d. Never read env vars directly outside `core/config.py`.
- Required external services for live API use: Redis, an OpenAI-compatible LLM endpoint from `LLM_BASE_URL`, ReNile API access/JWT, and the plant-disease prediction API from `PLANT_DISEASE_API_BASE_URL`.
- The speech-to-text subsystem is named ASR throughout: package `src/providers/ASR/`, settings `asr_*`, env keys `ASR_*`, `app.state.asr`, and `asr_*` log events. Existing `.env` files must rename `STT_*` to `ASR_*` and add `ASR_DTYPE` and `ASR_MAX_NEW_TOKENS`, or startup fails validation.
- `ASR_PROVIDER` selects the provider: `cohere` (local `CohereLabs/cohere-transcribe-arabic-07-2026` weights via `transformers`) or `faster_whisper`. `ASR_LANGUAGE` is required for `cohere`; the provider raises at construction when it is empty.
- The Cohere weights come from a gated Hugging Face repo, so a token with accepted conditions must be available (`HF_TOKEN` or `hf auth login`) before the model loads at startup.
- ASR/TTS models load eagerly during the lifespan, so app boot is slow and needs the weights reachable.
- Streamlit defaults to `CHAT_API_BASE_URL` or `http://localhost:8001`; `.env.example` uses `http://localhost:8000`, so verify the sidebar URL.

## Entrypoints
- FastAPI app: `src/main.py`; routes: `/health` and `POST /api/v1/chat`.
- `src/main.py`'s lifespan is the composition root: it builds every dependency once (Redis clients, LLM, ReNile client, plant-disease client, ASR, TTS) and hangs them on `app.state`. Nothing constructs its own providers; the agent receives clients through its constructor.
- The chat endpoint takes a bare `Request`, not a typed body. `services/chat_request_processor.py` branches on content type and normalizes JSON and multipart into one `ChatRequest`.
- JSON request schema is `jwt`, `conversation_id`, `message`. Multipart accepts `message`, `wav_file`, and/or `image_file`; `wav_file` is mutually exclusive with the other two, and at least one input is required.
- `wav_file` is transcribed into `message` before anything else runs, so the rest of the pipeline only ever sees text plus an optional `UploadedImage`.
- An image sent with no text gets a synthetic English marker message (`IMAGE_UPLOAD_MESSAGE`); `agent/graph.py` appends `IMAGE_ATTACHMENT_MARKER` when an image accompanies text. The prompt instructs the model to ignore bracketed markers when picking reply language.
- `image_file` must be `.jpeg/.jpg/.png/.webp` and within `PLANT_DISEASE_MAX_IMAGE_BYTES`; oversize uploads return 413, bad type or empty return 422.
- Voice replies are added after the agent returns, in `services/voice_response_processor.py`. TTS failure logs a warning and degrades to a text-only response.
- Response schema is `conversation_id`, `message`, plus optional `source`, `disease`, `audio_wav_base64`, `audio_content_type`. The endpoint sets `response_model_exclude_none=True`, so unused optional fields are absent from the payload.
- `streamlit_app.py` calls only `POST /api/v1/chat` and keeps display history locally.

## Agent And Tools
- Agent graph/prompt/tool routing live in `src/agent/graph.py` and `src/agent/prompts.py`; agent-visible tool schemas plus backend execution live in `src/agent/tools.py`.
- `graph.py` is a hand-rolled LangGraph-style loop, not LangGraph. Each round makes one LLM chat call with `OPENAI_TOOLS`, then `_tool_path()` routes on the **first** tool call's name to one of three nodes; tool calls outside the selected node's allowed set are skipped, not executed.
- Tool routing is name-based: `get_current_readings` goes to `current_tools`; `get_devices_ids`, `get_last_duration_summary`, and `get_specific_time_readings` go to `historical_tools`; `plant_diseases_detection` goes to `plant_disease_tools`.
- The loop is bounded by `MAX_TOOL_ROUNDS = 4`; falling off the end returns the fixed `FALLBACK_RESPONSE` string.
- JWT must never be exposed to LLM tool schemas, prompts, Redis memory, or logs; it is injected only during backend tool execution in `agent/tools.py::execute_tool`.
- Historical flows must call `get_devices_ids` before reading tools; historical tools require a real `device_id` resolved from the device list, never a device name.
- Device-ID resolution is the subtle part: the model routinely passes a device name or list ordinal instead of an `_id`. Before any historical tool runs, `_resolve_historical_arguments` fetches the device list (cache-first) and maps the raw value by exact id → ordinal → case-folded name. If it cannot resolve, it returns the device list *as the tool result* so the model re-asks, rather than calling ReNile with a bad ID.
- `get_last_duration_summary` calls ReNile `/api/v1/data/` with backend-fixed `data_type=month` and returns daily rows.
- `get_specific_time_readings` calls the same endpoint with backend-fixed `data_type=day` and returns hourly rows.
- `get_devices_ids` calls `RENILE_DEVICES_PATH` (`/api/users/devices/`) and returns a bare array of `{_id, name}`; `get_current_readings` calls `RENILE_CURRENT_READINGS_PATH` (`/api/users/reads`) and returns a `{project_name, generated_at, devices[]}` object. The backend returns both already cleaned, so they are passed to the agent unchanged — do not add client-side processing for them.
- `plant_diseases_detection` takes no model-supplied arguments. The image comes from agent state, so the graph fails the tool call when no image is attached, and `execute_tool` raises when the client or image is missing. It POSTs the image as multipart to `PLANT_DISEASE_PREDICT_PATH` and passes the prediction dict through unchanged.
- Plant-disease results bypass the Redis tool cache entirely; only ReNile tool results are cached.
- `chat_service.plant_disease_metadata` scrapes the returned `ToolContext` list for the `plant_diseases_detection` result and lifts `source`/`disease` onto `ChatResponse`.
- `execute_historical_readings_tool` / `get_historical_readings` is dead dummy-data code left in `tools.py`; it is not in `OPENAI_TOOLS` and not routed by the graph. Do not extend it.
- Agent orchestration uses regular LLM chat calls and supports bounded multi-tool historical follow-ups covered in `tests/test_agent_graph_routing.py`.

## Providers
- LLM, ReNile, and plant-disease are plain classes in `src/providers/`.
- ASR and TTS follow interface + factory + `providers/` (`src/providers/ASR/`, `src/providers/TTS/`). A new speech backend goes in that subpackage's `providers/` directory and is wired only in its `factory.py`.

## Memory And Cache
- Two Redis databases, deliberately separate. DB 0 stores only `user` and `assistant` messages in `conversation:{conversation_id}`; defaults are TTL `3600` seconds and max `12` messages.
- Redis DB 1 stores processed tool results as `tool_cache:{conversation_id}:{tool_name}:{arguments_hash}`; default TTL in `.env.example` is `600` seconds.
- Tool results are never written into prompt memory — the model only sees them within the round that fetched them. Tool execution checks the Redis tool cache before calling ReNile.

## Prompt Rules To Preserve
- The reply language is decided **only** from the text the user typed in the current message. Fully English text gets an English reply; Arabic or mixed Arabic/English gets Egyptian Arabic. Bracketed system markers, tool results, and earlier turns never change it. An image with no text follows the user's most recent text message, defaulting to Egyptian Arabic.
- Arabic text returned by tools (disease names, messages) must be restated in English when the reply is English, never pasted verbatim.
- Out-of-scope questions reply exactly — Arabic: `آسف، مقدرش أرد على سؤالك , أقدر بس اسعادك في قرائات مزرعتك وأمراض النباتات.` English: `Sorry, I can't answer that. I can only help with your farm readings and plant diseases.`
- Do not answer or call tools for farm/device readings before `2026-01-01`; reply exactly — Arabic: `القراءات قبل 2026 غير متاحة.` English: `Readings from before 2026 are not available.`
- The capability-help answer and the missing-data replies are fixed strings in both languages; keep both variants in sync when editing either.
- Any request carrying an uploaded plant image must call `plant_diseases_detection` before answering, and the reply branches on `is_plant` / `is_healthy` / `disease`.
- `src/agent/graph.py` rebuilds the system prompt per request with today's date appended, for relative dates like `امبارح`, `من يومين`, and `آخر أسبوع`.

## Test Update Map
- Tool schema changes: update `tests/test_tools.py` because it asserts no JWT or backend-fixed `data_type` exposure.
- Graph routing or tool orchestration changes: update `tests/test_agent_graph_routing.py`.
- Prompt/date/language/scope changes: update `tests/test_agent_memory_context.py`.
- Historical response processor changes (`src/services/historical_summary_processor.py`, now the only processor): update `tests/test_historical_summary_processor.py`.
- ASR provider or factory changes (`src/providers/ASR/`): update `tests/test_asr_factory.py`; it builds `Settings` from a literal dict so it never needs a local `.env`, and it must not download models or touch a GPU.
- Request parsing, endpoint, or response-shape changes: update `tests/test_chat_endpoint.py` and `tests/test_chat_schema.py`.
- Tests must stay hermetic: fakes only, no live Redis, LLM, ReNile, or plant-disease APIs, and no model downloads or GPU use.
