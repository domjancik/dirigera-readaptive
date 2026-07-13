from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

import yaml


class ProfileClient(Protocol):
    async def get_home(self) -> dict[str, Any]:
        ...

    async def update_adaptive_profile(self, profile_id: str, profile: dict[str, Any]) -> None:
        ...


ScheduleEntry = dict[str, int | str]


def load_schedule_file(path: Path) -> list[ScheduleEntry]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    schedule = raw.get("adaptiveSchedule")
    if not isinstance(schedule, list):
        raise ValueError("Schedule file must contain an adaptiveSchedule list.")
    return normalize_schedule(schedule)


async def update_profile_if_changed(
    client: ProfileClient,
    profile_id: str,
    schedule: list[ScheduleEntry],
    profile_name: str | None = None,
) -> bool:
    desired_schedule = normalize_schedule(schedule)
    home = await client.get_home()
    current_profile = _find_profile(home, profile_id)
    desired_name = profile_name or str(current_profile["name"])

    if (
        normalize_schedule(current_profile.get("adaptiveSchedule") or []) == desired_schedule
        and current_profile.get("name") == desired_name
    ):
        return False

    await client.update_adaptive_profile(
        profile_id,
        build_profile_update(current_profile, desired_schedule, profile_name=desired_name),
    )
    return True


def build_profile_update(
    current_profile: dict[str, Any],
    schedule: list[ScheduleEntry],
    profile_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": current_profile["id"],
        "name": profile_name or current_profile["name"],
        "adaptiveSchedule": normalize_schedule(schedule),
    }


def normalize_schedule(schedule: list[Any]) -> list[ScheduleEntry]:
    normalized = [_normalize_entry(entry) for entry in schedule]
    return sorted(normalized, key=lambda entry: str(entry["startTime"]))


def _normalize_entry(entry: Any) -> ScheduleEntry:
    if not isinstance(entry, dict):
        raise ValueError("Each schedule entry must be an object.")

    start_time = str(entry.get("startTime", ""))
    if not re.match(r"^[0-2][0-9]:[0-5][0-9]$", start_time):
        raise ValueError(f"Invalid startTime: {start_time}")
    hours = int(start_time[:2])
    if hours > 23:
        raise ValueError(f"Invalid startTime: {start_time}")

    light_level = int(entry["lightLevel"])
    if light_level < 1 or light_level > 100:
        raise ValueError("lightLevel must be between 1 and 100.")

    color_temperature = int(entry["colorTemperature"])
    if color_temperature < 1000 or color_temperature > 10000:
        raise ValueError("colorTemperature must be between 1000 and 10000.")

    return {
        "startTime": start_time,
        "lightLevel": light_level,
        "colorTemperature": color_temperature,
    }


def _find_profile(home: dict[str, Any], profile_id: str) -> dict[str, Any]:
    for profile in home.get("adaptiveProfiles") or []:
        if profile.get("id") == profile_id:
            return profile
    raise ValueError(f"Adaptive profile not found: {profile_id}")
