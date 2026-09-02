import logging
from time import perf_counter
from typing import Any

import httpx

from core.config import Settings

logger = logging.getLogger(__name__)


class PlantDiseaseClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.plant_disease_api_base_url
        self._predict_path = settings.plant_disease_predict_path
        self._timeout = settings.http_timeout_seconds

    async def predict(self, image_bytes: bytes, filename: str, content_type: str | None) -> dict[str, Any]:
        started_at = perf_counter()
        logger.info("plant_disease_predict_started path=%s filename=%s bytes=%s", self._predict_path, filename, len(image_bytes))
        files = {"file": (filename, image_bytes, content_type or "application/octet-stream")}
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.post(self._predict_path, files=files)
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.info(
                "plant_disease_predict_completed path=%s status_code=%s latency_ms=%s response_bytes=%s",
                self._predict_path,
                response.status_code,
                elapsed_ms,
                len(response.content),
            )
            response.raise_for_status()
            prediction = response.json()
        if not isinstance(prediction, dict):
            logger.error("plant_disease_predict_invalid_shape response_type=%s", type(prediction).__name__)
            raise ValueError("Unexpected plant disease prediction response shape")
        return prediction
