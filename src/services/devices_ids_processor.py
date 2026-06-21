import logging
from typing import Any

logger = logging.getLogger(__name__)


def process_devices_ids(devices_response: list[dict[str, Any]]) -> dict[str, Any]:
    logger.info("devices_ids_processing_started raw_devices=%s", len(devices_response))
    processed_devices = [_device_identity(device) for device in devices_response]
    devices = [device for device in processed_devices if device is not None]
    project_name = _project_name(devices_response)
    logger.info(
        "devices_ids_processing_completed project_name=%s processed_devices=%s",
        project_name,
        len(devices),
    )
    return {"project_name": project_name, "devices": devices}


def _project_name(devices_response: list[dict[str, Any]]) -> str | None:
    if not devices_response:
        return None
    project = devices_response[0].get("_project", {})
    if not isinstance(project, dict):
        return None
    return project.get("type")


def _device_identity(device: dict[str, Any]) -> dict[str, str] | None:
    device_name = device.get("name")
    device_id = device.get("id") or device.get("_id")
    if not device_name or not device_id:
        return None
    return {"device_name": device_name, "device_id": device_id}
