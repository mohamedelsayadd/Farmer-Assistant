# Repository Instructions

## Commands
- Use `uv` for all Python commands; do not use `pip` directly.
- Run tests with `uv run pytest`; run a focused test with `uv run pytest tests/test_tools.py` or `uv run pytest tests/test_tools.py::test_name`.
- Syntax-check backend code with `uv run python -m compileall src`; syntax-check the Streamlit client with `uv run python -m py_compile streamlit_app.py`.
- Start Redis and vLLM before running the API: `docker compose -f docker/compose.yaml up -d redis vllm`.
- Start the FastAPI app from the repo root with `uv run uvicorn main:app --reload`.
- Start the manual Streamlit tester with `uv run streamlit run streamlit_app.py`.

## Runtime Setup
- Settings load from root `.env` via `pydantic-settings`; keep real secrets only in `.env`, which is gitignored.
- `.env.example` is the source of expected env names. Important values: OpenAI-compatible LLM settings, Redis URL, ReNile base/path values, and `CHAT_API_BASE_URL` for Streamlit.
- Redis is required at app startup because `src/main.py` pings Redis in lifespan.
- Memory TTL is 1 hour and max memory messages is 12 unless `.env` changes it.

## Entrypoints
- FastAPI app: `src/main.py` exposes `/health` and includes `/api/v1/chat`.
- Chat request schema is `jwt`, `conversation_id`, `message`; response is only `conversation_id` and `message`.
- Manual UI: `streamlit_app.py` calls `POST /api/v1/chat` and keeps only UI-local display history.

## Agent And Tools
- Agent graph lives in `src/agent/graph.py`; tool schemas and execution live in `src/agent/tools.py`.
- Tool routing is split by name: `get_current_readings` goes to `current_tools`; `get_devices_ids`, `get_last_duration_summary`, and `get_specific_time_readings` go to `historical_tools`.
- JWT must never be exposed to LLM tool schemas, prompts, memory, or logs; it is injected only at backend tool execution.
- `get_devices_ids` is the mandatory device discovery tool for historical flows; historical tools require a `device_id` resolved from that context.
- `get_last_duration_summary` uses ReNile `/api/v1/data/` with backend-fixed `data_type=month` and returns daily rows.
- `get_specific_time_readings` uses the same endpoint with backend-fixed `data_type=day` and returns hourly rows.
- `get_current_readings` and `get_devices_ids` both use `/api/users/devices/` but different processors.

## Memory Behavior
- Redis stores `user`, `assistant`, and internal `tool_context` entries in one list keyed by `conversation:{conversation_id}`.
- Tool results are saved as `tool_context` after the user message and before the assistant response.
- Cached `tool_context` is injected into the next LLM call as `system` context, not as OpenAI `tool` role messages.

## Prompt And Date Handling
- The assistant must always answer in simple Egyptian Arabic.
- `src/agent/graph.py` injects today’s date into the system prompt so the LLM can resolve phrases like `امبارح`, `من يومين`, `آخر أسبوع`, and `يوم الأحد اللي فات`.
- For historical requests, the prompt tells the model to ask for device name first if the user did not provide one.

## Testing Notes
- Existing tests use fake Redis/client objects; do not require real Redis, vLLM, or ReNile APIs.
- After changing tool schemas, update `tests/test_tools.py` because it asserts no JWT/data_type exposure for agent-visible tools.
- After changing graph routing, update `tests/test_agent_graph_routing.py`.
- After changing response processors, update the matching processor tests under `tests/`.
