import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
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
ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


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
    # What the user actually typed (history + current message); register_complaint checks the phone against it.
    user_messages: list[str] = field(default_factory=list)


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
    Returns "devices", each with: id, name, connectivityType (WIFI or 4G), connectivityRenewType
    (automatic or manual, 4G only), expiration_date (manual 4G renewal only), and readings per sensor
    (value, unit, last_read_at, normal_range)."""
    # Always fetched fresh, then saved so later support turns see it in the support instructions.
    context = ctx.context
    result = await context.renile_client.get_devices_status(context.jwt)
    await context.tool_cache.set(
        conversation_id=context.conversation_id, tool_name="get_devices_status", arguments={}, result=result
    )
    return _dump("get_devices_status", result)


@function_tool(failure_error_function=tool_failed)
async def register_complaint(ctx: Context, device: str, name: str, phone: str, description: str) -> str:
    """Register a support complaint for one of the user's devices. Call it once, right before the Final Support Reply.
    Never call it until the user has written their name and phone number in this conversation.

    Args:
        device: The device name or id exactly as shown in get_devices_status.
        name: The user's name.
        phone: The user's phone number.
        description: Short Arabic summary of the problem and the check results.
    """
    context = ctx.context
    # The model has invented contact details before: only a phone the user actually typed is accepted.
    phone_digits = _digits(phone)
    if not phone_digits or not any(phone_digits in _digits(message) for message in context.user_messages):
        logger.warning("complaint_phone_not_from_user conversation_id=%s", context.conversation_id)
        return _dump("register_complaint", {"registered": False, "missing": "name_and_phone"})

    # Only the user's own devices (from their JWT-scoped status) may get a complaint; the API checks existence only.
    status = await _cached(
        context, "get_devices_status", {}, lambda: context.renile_client.get_devices_status(context.jwt)
    )
    devices = [{"_id": item.get("id"), "name": item.get("name")} for item in status["devices"]]
    device_id = resolve_device_id(str(device).strip(), devices)
    if device_id is None:
        logger.warning("complaint_unknown_device conversation_id=%s", context.conversation_id)
        return _dump("register_complaint", {"registered": False, "devices": [item["name"] for item in devices]})

    # API failures still end with the Final Support Reply, so they are reported here instead of via tool_failed.
    try:
        complaint = await context.renile_client.create_complaint(device_id, name, phone, description)
    except httpx.HTTPStatusError as error:
        if _invalid_field(error.response) == "phone":
            logger.warning("complaint_invalid_phone conversation_id=%s", context.conversation_id)
            return _dump("register_complaint", {"registered": False, "invalid_field": "phone"})
        logger.error(
            "complaint_failed conversation_id=%s status_code=%s", context.conversation_id, error.response.status_code
        )
        return _dump("register_complaint", {"registered": False})
    except httpx.HTTPError as error:
        logger.error("complaint_failed conversation_id=%s error_type=%s", context.conversation_id, type(error).__name__)
        return _dump("register_complaint", {"registered": False})
    logger.info("complaint_registered conversation_id=%s complaint_id=%s", context.conversation_id, complaint.get("id"))
    return _dump("register_complaint", {"registered": True})


TOOLS = [
    plant_diseases_detection,
    get_current_readings,
    get_devices_ids,
    get_last_duration_summary,
    get_specific_time_readings,
]

SUPPORT_TOOLS = [get_devices_status, register_complaint]


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


def _digits(text: str) -> str:
    return "".join(char for char in text.translate(ARABIC_INDIC_DIGITS) if char.isdigit())


def _invalid_field(response: httpx.Response) -> str | None:
    if response.status_code != 400:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("field") if isinstance(body, dict) else None


def _dump(tool_name: str, result: Any) -> str:
    logger.info("tool_call_completed tool_name=%s result_preview=%s", tool_name, json_preview(result))
    return json.dumps(result, ensure_ascii=False)
