from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .schedule_update import ProfileClient, ScheduleEntry, update_profile_if_changed
from .seasonal_schedule import (
    CurveConfig,
    generate_adaptive_schedule,
    schedule_yaml_document,
    sun_times_for_date,
)


@dataclass(frozen=True)
class ScheduleProfileTarget:
    name: str
    profile_name: str
    profile_id: str | None
    output: Path | None
    curve: CurveConfig


@dataclass(frozen=True)
class ScheduleProfilesConfig:
    target_date: date
    latitude: float
    longitude: float
    timezone: str
    sample_minutes: int
    profiles: list[ScheduleProfileTarget]


def load_schedule_profiles_config(path: Path) -> ScheduleProfilesConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = raw.get("schedule_updates") or {}
    if not isinstance(section, dict):
        raise ValueError("schedule_updates must be an object.")

    raw_profiles = section.get("profiles") or []
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ValueError("schedule_updates.profiles must contain at least one profile.")

    target_date = date.fromisoformat(str(section.get("date", date.today().isoformat())))
    return ScheduleProfilesConfig(
        target_date=target_date,
        latitude=float(section["latitude"]),
        longitude=float(section["longitude"]),
        timezone=str(section["timezone"]),
        sample_minutes=int(section.get("sample_minutes", 30)),
        profiles=[_profile_target(item) for item in raw_profiles],
    )


async def update_configured_profiles(
    client: ProfileClient,
    config: ScheduleProfilesConfig,
) -> dict[str, bool]:
    sun_times = sun_times_for_date(
        config.target_date,
        latitude=config.latitude,
        longitude=config.longitude,
        timezone_name=config.timezone,
    )

    results = {}
    for target in config.profiles:
        schedule = generate_adaptive_schedule(
            sun_times,
            target.curve,
            sample_interval_minutes=config.sample_minutes,
        )
        if target.output:
            _write_schedule_file(target.output, schedule)
        profile_name = f"{target.profile_name} {config.target_date.isoformat()}"
        profile_id, created = await _resolve_profile_id(
            client,
            target,
            schedule,
            profile_name,
        )
        updated = await update_profile_if_changed(
            client,
            profile_id,
            schedule,
            profile_name=profile_name,
        )
        results[target.name] = created or updated
    return results


def _profile_target(raw: Any) -> ScheduleProfileTarget:
    if not isinstance(raw, dict):
        raise ValueError("Each schedule profile must be an object.")

    output = raw.get("output")
    return ScheduleProfileTarget(
        name=str(raw["name"]),
        profile_name=str(raw.get("profile_name", raw["name"])),
        profile_id=str(raw["profile_id"]) if raw.get("profile_id") else None,
        output=Path(str(output)) if output else None,
        curve=_curve_config(raw.get("curve") or {}),
    )


async def _resolve_profile_id(
    client: ProfileClient,
    target: ScheduleProfileTarget,
    schedule: list[ScheduleEntry],
    profile_name: str,
) -> tuple[str, bool]:
    if target.profile_id:
        return target.profile_id, False

    home = await client.get_home()
    matches = _matching_profiles(home, target.profile_name)
    if len(matches) == 1:
        return str(matches[0]["id"]), False
    if len(matches) > 1:
        raise ValueError(f"Multiple adaptive profiles match {target.profile_name!r}.")

    create_profile = getattr(client, "create_adaptive_profile", None)
    if create_profile is None:
        raise ValueError("Profile client cannot create an adaptive profile.")
    await create_profile({"name": profile_name, "adaptiveSchedule": schedule})

    home = await client.get_home()
    matches = _matching_profiles(home, target.profile_name)
    if len(matches) != 1:
        raise ValueError(f"Created adaptive profile {profile_name!r} was not found.")
    return str(matches[0]["id"]), True


def _matching_profiles(home: dict[str, Any], profile_name: str) -> list[dict[str, Any]]:
    prefix = f"{profile_name} "
    return [
        profile
        for profile in home.get("adaptiveProfiles") or []
        if profile.get("name") == profile_name
        or (
            isinstance(profile.get("name"), str)
            and str(profile["name"]).startswith(prefix)
            and len(str(profile["name"])) == len(prefix) + 10
        )
    ]


def _curve_config(raw: dict[str, Any]) -> CurveConfig:
    if not isinstance(raw, dict):
        raise ValueError("curve must be an object.")

    allowed = {field.name for field in fields(CurveConfig)}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"Unknown curve setting(s): {', '.join(unknown)}")
    return CurveConfig(**raw)


def _write_schedule_file(path: Path, schedule: list[ScheduleEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(schedule_yaml_document(schedule), sort_keys=False),
        encoding="utf-8",
    )
