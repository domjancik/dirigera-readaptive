from __future__ import annotations

import asyncio
import ssl
from collections.abc import AsyncIterator
from typing import Any

import requests
import urllib3
import websockets

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class HttpDirigeraClient:
    def __init__(
        self,
        host: str,
        token: str,
        port: int = 8443,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = f"https://{host}:{port}/v1"
        self._ws_url = f"wss://{host}:{port}/v1"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._session = session or requests.Session()

    async def get_device(self, device_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_device_sync, device_id)

    async def get_devices(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_devices_sync)

    async def activate_adaptive(self, device_id: str, profile_id: str) -> None:
        await asyncio.to_thread(self._activate_adaptive_sync, device_id, profile_id)

    async def get_home(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_home_sync)

    async def update_adaptive_profile(self, profile_id: str, profile: dict[str, Any]) -> None:
        await asyncio.to_thread(self._update_adaptive_profile_sync, profile_id, profile)

    async def events(self) -> AsyncIterator[str]:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with websockets.connect(
            self._ws_url,
            additional_headers=self._headers,
            ssl=ssl_context,
            ping_interval=30,
        ) as websocket:
            async for message in websocket:
                yield str(message)

    def _get_device_sync(self, device_id: str) -> dict[str, Any]:
        response = self._session.get(
            f"{self._base_url}/devices/{device_id}",
            headers=self._headers,
            timeout=10,
            verify=False,
        )
        response.raise_for_status()
        return response.json()

    def _get_devices_sync(self) -> list[dict[str, Any]]:
        response = self._session.get(
            f"{self._base_url}/devices",
            headers=self._headers,
            timeout=10,
            verify=False,
        )
        response.raise_for_status()
        return response.json()

    def _get_home_sync(self) -> dict[str, Any]:
        response = self._session.get(
            f"{self._base_url}/home",
            headers=self._headers,
            timeout=10,
            verify=False,
        )
        response.raise_for_status()
        return response.json()

    def _activate_adaptive_sync(self, device_id: str, profile_id: str) -> None:
        response = self._session.patch(
            f"{self._base_url}/devices/{device_id}",
            headers=self._headers,
            json=[{"adaptiveProfile": {"id": profile_id, "active": True}}],
            timeout=10,
            verify=False,
        )
        response.raise_for_status()

    def _update_adaptive_profile_sync(self, profile_id: str, profile: dict[str, Any]) -> None:
        response = self._session.put(
            f"{self._base_url}/adaptive-profiles/{profile_id}",
            headers=self._headers,
            json=profile,
            timeout=10,
            verify=False,
        )
        response.raise_for_status()
