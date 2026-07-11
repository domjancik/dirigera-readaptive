from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class DirigeraClient(Protocol):
    async def get_device(self, device_id: str) -> dict[str, Any]:
        ...

    async def activate_adaptive(self, device_id: str, profile_id: str) -> None:
        ...


SleepFn = Callable[[float], Awaitable[None]]
NowFn = Callable[[], float]


@dataclass(frozen=True)
class LightConfig:
    id: str
    adaptive_profile_id: str | None = None
    reconnect_delay_ms: int = 1000


class RecoveryDaemon:
    def __init__(
        self,
        client: DirigeraClient,
        lights: Sequence[LightConfig],
        cooldown_seconds: int,
        recover_on_reconnect: bool = True,
        recover_on_power_on: bool = False,
        now: NowFn | None = None,
        sleep: SleepFn | None = None,
    ) -> None:
        self._client = client
        self._lights = {light.id: light for light in lights}
        self._cooldown_seconds = cooldown_seconds
        self._recover_on_reconnect = recover_on_reconnect
        self._recover_on_power_on = recover_on_power_on
        self._now = now or time.monotonic
        self._sleep = sleep or asyncio.sleep
        self._reachable: dict[str, bool] = {}
        self._is_on: dict[str, bool] = {}
        self._last_activation_at: dict[str, float] = {}

    async def handle_reachability(self, device_id: str, is_reachable: bool) -> None:
        await self.handle_device_state(device_id, is_reachable=is_reachable)

    async def handle_device_state(
        self,
        device_id: str,
        is_reachable: bool | None = None,
        is_on: bool | None = None,
    ) -> None:
        if device_id not in self._lights:
            return

        previous_reachable = self._reachable.get(device_id)
        previous_is_on = self._is_on.get(device_id)

        if is_reachable is not None:
            self._reachable[device_id] = is_reachable
        if is_on is not None:
            self._is_on[device_id] = is_on

        reconnected = (
            self._recover_on_reconnect
            and previous_reachable is False
            and is_reachable is True
        )
        powered_on = (
            self._recover_on_power_on
            and previous_is_on is False
            and is_on is True
        )
        if reconnected or powered_on:
            await self._recover_light(device_id)

    async def poll_once(self) -> None:
        for device_id in self._lights:
            device = await self._client.get_device(device_id)
            reachable = bool(device.get("isReachable"))
            is_on = bool(device.get("attributes", {}).get("isOn"))
            await self.handle_device_state(device_id, is_reachable=reachable, is_on=is_on)

    async def _recover_light(self, device_id: str) -> None:
        if self._is_in_cooldown(device_id):
            return

        light = self._lights[device_id]
        await self._sleep(light.reconnect_delay_ms / 1000)

        device = await self._client.get_device(device_id)
        if not device.get("isReachable"):
            return
        if not device.get("attributes", {}).get("isOn"):
            return

        profile_id = self._profile_id_for(light, device)
        if not profile_id:
            return

        await self._activate_with_retry(device_id, profile_id)
        self._last_activation_at[device_id] = self._now()

    async def _activate_with_retry(self, device_id: str, profile_id: str) -> None:
        delay_seconds = 0.5
        for attempt in range(3):
            try:
                await self._client.activate_adaptive(device_id, profile_id)
                return
            except Exception:
                if attempt == 2:
                    raise
                await self._sleep(delay_seconds)
                delay_seconds *= 2

    def _is_in_cooldown(self, device_id: str) -> bool:
        last_activation = self._last_activation_at.get(device_id)
        if last_activation is None:
            return False
        return self._now() - last_activation < self._cooldown_seconds

    @staticmethod
    def _profile_id_for(light: LightConfig, device: dict[str, Any]) -> str | None:
        if light.adaptive_profile_id:
            return light.adaptive_profile_id

        behavior = device.get("attributes", {}).get("deviceOnBehavior") or {}
        if behavior.get("behavior") == "adaptiveProfile" and behavior.get("profileId"):
            return str(behavior["profileId"])

        active_profile = device.get("adaptiveProfile") or {}
        if active_profile.get("id"):
            return str(active_profile["id"])

        return None
