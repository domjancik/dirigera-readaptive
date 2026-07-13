import json

from dirigera_readaptive.events import device_state_updates, reachability_updates


def test_reachability_updates_find_nested_device_updates():
    message = json.dumps(
        {
            "type": "deviceStateChanged",
            "data": {
                "devices": [
                    {"id": "light-1", "isReachable": False},
                    {"id": "light-2", "attributes": {"isOn": True}},
                ]
            },
        }
    )

    assert reachability_updates(message) == [("light-1", False)]


def test_reachability_updates_ignore_invalid_json():
    assert reachability_updates("not json") == []


def test_device_state_updates_include_is_on():
    message = json.dumps(
        {
            "data": {
                "id": "light-1",
                "isReachable": True,
                "attributes": {"isOn": True},
            }
        }
    )

    assert device_state_updates(message) == [
        ("light-1", {"is_reachable": True, "is_on": True})
    ]


def test_device_state_updates_include_last_seen_from_reachability_event():
    message = json.dumps(
        {
            "type": "deviceStateChanged",
            "data": {
                "deviceType": "light",
                "id": "light-1",
                "isReachable": True,
                "lastSeen": "2026-07-13T07:23:47.000Z",
            },
        }
    )

    assert device_state_updates(message) == [
        (
            "light-1",
            {
                "is_reachable": True,
                "last_seen": "2026-07-13T07:23:47.000Z",
            },
        )
    ]
