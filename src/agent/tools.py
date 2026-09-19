import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from pydantic import Field

from core.logging import json_preview
from memory.tool_cache import ToolCache
from models.schemas.chat import UploadedImage
from providers.plant_disease_client import PlantDiseaseClient
from providers.renile_client import ReNileClient
from services.historical_summary_processor import process_daily_sensor_response, process_hourly_sensor_response

logger = logging.getLogger(__name__)

ToolResult = dict[str, Any] | list[dict[str, Any]]


@dataclass(frozen=True)
class AgentContext:
    """Per-request runtime context. Injected into tools and never shown to the model."""

    conversation_id: str
    jwt: str
    renile_client: ReNileClient
    tool_cache: ToolCache
    plant_disease_client: PlantDiseaseClient | None = None
    image: UploadedImage | None = None


Runtime = ToolRuntime[AgentContext]
DeviceId = Annotated[
    str,
    Field(description="Real device_id copied from get_devices_ids context. This must be an ID, not the device name."),
]


@tool(
    description="Diagnose an uploaded plant image for disease. "
    "Use when the current user request includes a plant image upload."
)
async def plant_diseases_detection(runtime: Runtime) -> str:
    context = runtime.context
    if context.plant_disease_client is None or context.image is None:
        raise ValueError("plant_diseases_detection requires an uploaded image")
    image = context.image
    logger.info("tool_plant_diseases_detection_started filename=%s bytes=%s", image.filename, len(image.content))
    # Plant-disease results bypass the tool cache: every upload is a new image.
    prediction = await context.plant_disease_client.predict(
        image_bytes=image.content,
        filename=image.filename,
        content_type=image.content_type,
    )
    return _dump("plant_diseases_detection", prediction)


@tool(description="Get the latest farm sensor readings. Use for current, now, latest, or live readings questions.")
async def get_current_readings(runtime: Runtime) -> str:
    context = runtime.context
    result = await _cached(context, "get_current_readings", {}, lambda: context.renile_client.get_current_readings(context.jwt))
    return _dump("get_current_readings", result)


@tool(
    description="Get the user's available farm devices and their IDs. "
    "Required before answering historical readings questions."
)
async def get_devices_ids(runtime: Runtime) -> str:
    return _dump("get_devices_ids", await _devices(runtime.context))


@tool(
    description="Get historical daily summary readings for a selected device and period. "
    "Use only after get_devices_ids returned the real device_id. NEVER pass a device name as device_id."
)
async def get_last_duration_summary(
    device_id: DeviceId,
    start_time: Annotated[
        str,
        Field(description="Start time in format YYYY-MM-DD HH:mm, resolved using today's date from the system prompt."),
    ],
    runtime: Runtime,
) -> str:
    async def fetch(resolved_id: str) -> dict[str, Any]:
        raw = await runtime.context.renile_client.get_last_duration_summary(
            jwt=runtime.context.jwt, device_id=resolved_id, start_time=start_time
        )
        rows = process_daily_sensor_response(raw)
        return {"device_id": resolved_id, "start_time": start_time, "data_type": "month", "daily_rows": rows}

    return await _historical("get_last_duration_summary", runtime.context, device_id, start_time, fetch)


@tool(
    description="Get historical hourly readings for a selected device on a specific previous day or time. "
    "Use only after get_devices_ids returned the real device_id. NEVER pass a device name as device_id."
)
async def get_specific_time_readings(
    device_id: DeviceId,
    start_time: Annotated[
        str,
        Field(
            description="Specific day start time in format YYYY-MM-DD HH:mm, "
            "resolved using today's date from the system prompt."
        ),
    ],
    runtime: Runtime,
) -> str:
    async def fetch(resolved_id: str) -> dict[str, Any]:
        raw = await runtime.context.renile_client.get_specific_time_readings(
            jwt=runtime.context.jwt, device_id=resolved_id, start_time=start_time
        )
        rows = process_hourly_sensor_response(raw)
        return {"device_id": resolved_id, "start_time": start_time, "data_type": "day", "hourly_rows": rows}

    return await _historical("get_specific_time_readings", runtime.context, device_id, start_time, fetch)


TOOLS = [
    plant_diseases_detection,
    get_current_readings,
    get_devices_ids,
    get_last_duration_summary,
    get_specific_time_readings,
]


async def _historical(
    tool_name: str,
    context: AgentContext,
    raw_device_id: str,
    start_time: str,
    fetch: Callable[[str], Awaitable[dict[str, Any]]],
) -> str:
    # The model often passes a device name or list ordinal instead of an _id. Resolve it
    # against the device list; if that fails, hand the list back so the model re-asks.
    devices = await _devices(context)
    resolved_id = resolve_device_id(str(raw_device_id).strip(), devices) if isinstance(devices, list) else None
    if resolved_id is None:
        logger.warning("historical_device_resolution_failed raw_device_id=%s", raw_device_id)
        return _dump(tool_name, devices)

    arguments = {"device_id": resolved_id, "start_time": start_time}
    return _dump(tool_name, await _cached(context, tool_name, arguments, lambda: fetch(resolved_id)))


async def _devices(context: AgentContext) -> Any:
    return await _cached(context, "get_devices_ids", {}, lambda: context.renile_client.get_devices_ids(context.jwt))


async def _cached(
    context: AgentContext,
    tool_name: str,
    arguments: dict[str, Any],
    fetch: Callable[[], Awaitable[ToolResult]],
) -> ToolResult:
    cached = await context.tool_cache.get(conversation_id=context.conversation_id, tool_name=tool_name, arguments=arguments)
    if cached is not None:
        return cached
    result = await fetch()
    await context.tool_cache.set(
        conversation_id=context.conversation_id, tool_name=tool_name, arguments=arguments, result=result
    )
    return result


def resolve_device_id(raw_device_id: str, devices: list[dict[str, Any]]) -> str | None:
    """Map a raw model value to a real device _id: exact id, then 1-based ordinal, then case-folded name."""
    if not raw_device_id:
        return None
    for device in devices:
        device_id = str(device.get("_id", "")).strip()
        if raw_device_id == device_id:
            return device_id

    # Enumerate the full array: the model numbers the list it was shown verbatim,
    # so skipping entries here would shift indices against its numbering.
    lowered_raw_device_id = raw_device_id.casefold()
    for index, device in enumerate(devices, start=1):
        device_name = str(device.get("name", "")).strip()
        device_id = str(device.get("_id", "")).strip()
        if not device_id:
            continue
        if raw_device_id == str(index) or lowered_raw_device_id == device_name.casefold():
            return device_id
    return None


def _dump(tool_name: str, result: Any) -> str:
    logger.info("tool_call_completed tool_name=%s result_preview=%s", tool_name, json_preview(result))
    return json.dumps(result, ensure_ascii=False)
