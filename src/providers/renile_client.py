from typing import Any

import httpx

from core.config import Settings


class ReNileClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.renile_api_base_url
        self._current_path = settings.renile_current_readings_path
        self._historical_path = settings.renile_historical_readings_path
        self._timeout = settings.http_timeout_seconds

    async def get_current_readings(self, jwt: str, params: dict[str, Any]) -> dict[str, Any]:
        return await self._get(self._current_path, jwt, params)

    async def get_historical_readings(self, jwt: str, params: dict[str, Any]) -> dict[str, Any]:
        return await self._get(self._historical_path, jwt, params)

    async def _get(self, path: str, jwt: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {jwt}"}
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.get(path, params={k: v for k, v in params.items() if v is not None}, headers=headers)
            response.raise_for_status()
            return response.json()
