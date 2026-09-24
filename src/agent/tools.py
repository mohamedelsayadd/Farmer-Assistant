import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from agents import ModelBehaviorError, RunContextWrapper, function_tool

from core.logging import json_preview
from memory.tool_cache import ToolCache
from models.schemas.chat import UploadedImage
from providers.plant_disease_client import PlantDiseaseClient
from providers.renile_client import ReNileClient
from services.historical_summary_processor import process_daily_sensor_response, process_hourly_sensor_response

logger = logging.getLogger(__name__)

ToolResult = dict[str, Any] | list[dict[str, Any]]
TOOL_FAILED_MESSAGE = "Tool failed temporarily."


@dataclass
class AgentContext:
    """Per-request runtime context. Injected into tools and never shown to the model."""

    conversation_id: str
    jwt: str
    renile_client: ReNileClient
    tool_cache: ToolCache
    plant_disease_client: PlantDiseaseClient | None = None
    image: UploadedImage | None = None
    # Set by plant_diseases_detection; ChatService lifts source/disease from it onto the response.
    plant_prediction: dict[str, Any] | None = None


Context = RunContextWrapper[AgentContext]


def tool_failed(ctx: RunContextWrapper[Any], error: Exception) -> str:
    # Upstream/argument failures go back to the model so it can continue; anything
    # else (e.g. RedisError) is re-raised and reaches ChatService.
    if not isinstance(error, (ValueError, httpx.HTTPError, ModelBehaviorError)):
        raise error
    logger.error("tool_call_failed error_type=%s", type(error).__name__, exc_info=error)
    return TOOL_FAILED_MESSAGE


@function_tool(failure_error_function=tool_failed)
async def plant_diseases_detection(ctx: Context) -> str:
    """Diagnose an uploaded plant image for disease. Use when the current user request includes a plant image upload."""
    context = ctx.context
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
    context.plant_prediction = prediction
    return _dump("plant_diseases_detection", prediction)


@function_tool(failure_error_function=tool_failed)
async def get_current_readings(ctx: Context) -> str:
    """Get the latest farm sensor readings. Use for current, now, latest, or live readings questions."""
    context = ctx.context
    result = await _cached(context, "get_current_readings", {}, lambda: context.renile_client.get_current_readings(context.jwt))
    return _dump("get_current_readings", result)


@function_tool(failure_error_function=tool_failed)
async def get_devices_ids(ctx: Context) -> str:
    """Get the user's available farm devices and their IDs. Required before answering historical readings questions."""
    return _dump("get_devices_ids", await _devices(ctx.context))


@function_tool(failure_error_function=tool_failed)
async def get_last_duration_summary(ctx: Context, device_id: str, start_time: str) -> str:
    """Get historical daily summary readings for a selected device and period.
    Use only after get_devices_ids returned the real device_id. NEVER pass a device name as device_id.

    Args:
        device_id: Real device_id copied from get_devices_ids context. This must be an ID, not the device name.
        start_time: Start time in format YYYY-MM-DD HH:mm, resolved using today's date from the system prompt.
    """

    async def fetch(resolved_id: str) -> dict[str, Any]:
        raw = await ctx.context.renile_client.get_last_duration_summary(
            jwt=ctx.context.jwt, device_id=resolved_id, start_time=start_time
        )
        rows = process_daily_sensor_response(raw)
        return {"device_id": resolved_id, "start_time": start_time, "data_type": "month", "daily_rows": rows}

    return await _historical("get_last_duration_summary", ctx.context, device_id, start_time, fetch)


@function_tool(failure_error_function=tool_failed)
async def get_specific_time_readings(ctx: Context, device_id: str, start_time: str) -> str:
    """Get historical hourly readings for a selected device on a specific previous day or time.
    Use only after get_devices_ids returned the real device_id. NEVER pass a device name as device_id.

    Args:
        device_id: Real device_id copied from get_devices_ids context. This must be an ID, not the device name.
        start_time: Specific day start time in format YYYY-MM-DD HH:mm, resolved using today's date from the system prompt.
    """

    async def fetch(resolved_id: str) -> dict[str, Any]:
        raw = await ctx.context.renile_client.get_specific_time_readings(
            jwt=ctx.context.jwt, device_id=resolved_id, start_time=start_time
        )
        rows = process_hourly_sensor_response(raw)
        return {"device_id": resolved_id, "start_time": start_time, "data_type": "day", "hourly_rows": rows}

    return await _historical("get_specific_time_readings", ctx.context, device_id, start_time, fetch)


@function_tool(failure_error_function=tool_failed)
async def get_devices_status(ctx: Context) -> str:
    """Get the status of each of the user's devices, for troubleshooting a device problem the user reported.
    Returns per device: _id, name, last_reading_time, readings (sensor values), connection_type (WIFI or 4G),
    renewal_type (automatic or manual, 4G only), and renewal_date (manual 4G renewal only)."""
    # Not cached: troubleshooting needs the freshest status.
    context = ctx.context
    return _dump("get_devices_status", await context.renile_client.get_devices_status(context.jwt))


TOOLS = [
    plant_diseases_detection,
    get_current_readings,
    get_devices_ids,
    get_last_duration_summary,
    get_specific_time_readings,
]

SUPPORT_TOOLS = [get_devices_status]


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
