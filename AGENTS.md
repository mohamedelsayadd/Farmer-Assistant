# Repository Instructions

## Commands
- Use `uv` for Python work; do not use `pip` directly. Install/sync with `uv sync`.
- Run all tests with `uv run pytest`; run focused tests with `uv run pytest tests/test_tools.py` or `uv run pytest tests/test_tools.py::test_name`.
- Syntax-check backend code with `uv run python -m compileall src`; syntax-check the Streamlit client with `uv run python -m py_compile streamlit_app.py`.
- Start local Redis with `docker compose -f docker/compose.yaml up -d redis`. This compose file does not start an LLM server.
- Start the FastAPI app from the repo root with `uv run uvicorn main:app --reload`; startup pings Redis DB 0 and DB 1.
- Start the manual tester with `uv run streamlit run streamlit_app.py`.

## Runtime Setup
- Settings load from root `.env` via `pydantic-settings`; `.env.example` is the verified list of env names. Keep real secrets only in `.env`.
- `.env` is the single source of truth: `src/core/config.py` declares no in-code defaults, so every key in `.env.example` is required and a missing one fails validation at startup. Add a new setting to `.env` and `.env.example` in the same change as the `Settings` field.
- Required external services for live API use: Redis, an OpenAI-compatible LLM endpoint from `LLM_BASE_URL`, and ReNile API access/JWT.
- Streamlit defaults to `CHAT_API_BASE_URL` or `http://localhost:8001`; `.env.example` uses `http://localhost:8000`, so verify the sidebar URL.

## Entrypoints
- FastAPI app: `src/main.py`; routes: `/health` and `POST /api/v1/chat`.
- Chat request schema is `jwt`, `conversation_id`, `message`; response schema is `conversation_id`, `message`.
- `streamlit_app.py` calls only `POST /api/v1/chat` and keeps display history locally.

## Agent And Tools
- Agent graph/prompt/tool routing live in `src/agent/graph.py` and `src/agent/prompts.py`; agent-visible tool schemas plus backend execution live in `src/agent/tools.py`.
- Tool routing is name-based: `get_current_readings` goes to `current_tools`; `get_devices_ids`, `get_last_duration_summary`, and `get_specific_time_readings` go to `historical_tools`.
- JWT must never be exposed to LLM tool schemas, prompts, Redis memory, or logs; it is injected only during backend tool execution.
- Historical flows must call `get_devices_ids` before reading tools; historical tools require a real `device_id` resolved from the device list, never a device name.
- `get_last_duration_summary` calls ReNile `/api/v1/data/` with backend-fixed `data_type=month` and returns daily rows.
- `get_specific_time_readings` calls the same endpoint with backend-fixed `data_type=day` and returns hourly rows.
- `get_devices_ids` calls `RENILE_DEVICES_PATH` (`/api/users/devices/`) and returns a bare array of `{_id, name}`; `get_current_readings` calls `RENILE_CURRENT_READINGS_PATH` (`/api/users/reads`) and returns a `{project_name, generated_at, devices[]}` object. The backend returns both already cleaned, so they are passed to the agent unchanged — do not add client-side processing for them.
- Agent orchestration uses regular LLM chat calls and supports bounded multi-tool historical follow-ups covered in `tests/test_agent_graph_routing.py`.

## Memory And Cache
- Redis DB 0 stores only `user` and `assistant` messages in `conversation:{conversation_id}`; defaults are TTL `3600` seconds and max `12` messages.
- Redis DB 1 stores processed tool results as `tool_cache:{conversation_id}:{tool_name}:{arguments_hash}`; default TTL in `.env.example` is `600` seconds.
- Tool results are not injected into prompt memory. Tool execution checks Redis tool cache before calling ReNile.

## Prompt Rules To Preserve
- Fully English user messages should get English replies; Arabic or mixed Arabic/English should get Egyptian Arabic replies.
- Out-of-scope questions should reply exactly: `آسف، مقدرش أرد على سؤالك.`
- Do not answer or call tools for farm/device readings before `2026-01-01`; reply exactly: `القراءات قبل 2026 غير متاحة.`
- `src/agent/graph.py` injects today’s date into the system prompt for relative dates like `امبارح`, `من يومين`, and `آخر أسبوع`.

## Test Update Map
- Tool schema changes: update `tests/test_tools.py` because it asserts no JWT or backend-fixed `data_type` exposure.
- Graph routing or tool orchestration changes: update `tests/test_agent_graph_routing.py`.
- Prompt/date/language/scope changes: update `tests/test_agent_memory_context.py`.
- Historical response processor changes (`src/services/historical_summary_processor.py`, now the only processor): update `tests/test_historical_summary_processor.py`.
- Existing tests use fakes and should not require live Redis, LLM, or ReNile APIs.
