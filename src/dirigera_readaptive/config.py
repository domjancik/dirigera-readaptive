from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .recovery import LightConfig


@dataclass(frozen=True)
class DirigeraConfig:
    host: str
    token: str


@dataclass(frozen=True)
class AppConfig:
    dirigera: DirigeraConfig
    lights: list[LightConfig]
    poll_interval_seconds: int = 10
    activation_cooldown_seconds: int = 30
    recover_on_reconnect: bool = True
    recover_on_power_on: bool = False


def load_config(path: Path) -> AppConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    dirigera = raw.get("dirigera") or {}
    token = load_dirigera_token(dirigera)

    lights_raw = raw.get("lights") or []
    lights = [_light_config(item) for item in lights_raw]
    if not lights:
        raise ValueError("At least one light must be configured.")

    return AppConfig(
        dirigera=DirigeraConfig(host=str(dirigera["host"]), token=token),
        lights=lights,
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 10)),
        activation_cooldown_seconds=int(raw.get("activation_cooldown_seconds", 30)),
        recover_on_reconnect=bool(raw.get("recover_on_reconnect", True)),
        recover_on_power_on=bool(raw.get("recover_on_power_on", False)),
    )


def load_dirigera_token(dirigera: dict[str, Any]) -> str:
    token_env = str(dirigera.get("token_env", "DIRIGERA_TOKEN"))
    token = os.environ.get(token_env)
    if token:
        return token

    token_file = dirigera.get("token_file")
    if token_file:
        token = Path(str(token_file)).read_text(encoding="utf-8").strip()
        if token:
            return token
        raise ValueError(f"Token file {token_file} is empty.")

    raise ValueError(
        f"Environment variable {token_env} must contain the DIRIGERA token, "
        "or dirigera.token_file must point to a token file."
    )


def _light_config(raw: dict[str, Any]) -> LightConfig:
    return LightConfig(
        id=str(raw["id"]),
        adaptive_profile_id=raw.get("adaptive_profile_id"),
        reconnect_delay_ms=int(raw.get("reconnect_delay_ms", 1000)),
        reconnect_retry_delay_ms=int(raw.get("reconnect_retry_delay_ms", 1000)),
        reconnect_attempts=int(raw.get("reconnect_attempts", 6)),
    )
