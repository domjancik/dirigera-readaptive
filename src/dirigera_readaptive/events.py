from __future__ import annotations

import json
from typing import Any


DeviceState = dict[str, bool | str]


def reachability_updates(message: str) -> list[tuple[str, bool]]:
    return [
        (device_id, state["is_reachable"])
        for device_id, state in device_state_updates(message)
        if "is_reachable" in state
    ]


def device_state_updates(message: str) -> list[tuple[str, DeviceState]]:
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return []

    updates: list[tuple[str, DeviceState]] = []
    _collect_device_state(payload, updates)
    return updates


def _collect_device_state(value: Any, updates: list[tuple[str, DeviceState]]) -> None:
    if isinstance(value, dict):
        if isinstance(value.get("id"), str):
            state: DeviceState = {}
            if isinstance(value.get("isReachable"), bool):
                state["is_reachable"] = value["isReachable"]
            if isinstance(value.get("lastSeen"), str):
                state["last_seen"] = value["lastSeen"]
            attributes = value.get("attributes") or {}
            if isinstance(attributes, dict) and isinstance(attributes.get("isOn"), bool):
                state["is_on"] = attributes["isOn"]
            if state:
                updates.append((value["id"], state))
        for child in value.values():
            _collect_device_state(child, updates)
    elif isinstance(value, list):
        for child in value:
            _collect_device_state(child, updates)
