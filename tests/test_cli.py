import asyncio
import json
import logging

from dirigera_readaptive import cli


def test_configure_logging_enables_info_audit_entries(monkeypatch):
    calls = []

    logging_module = getattr(cli, "logging", logging)
    monkeypatch.setattr(logging_module, "basicConfig", lambda **kwargs: calls.append(kwargs))
    configure_logging = getattr(cli, "configure_logging", None)

    assert configure_logging is not None
    configure_logging()

    assert calls == [
        {
            "level": logging.INFO,
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
        }
    ]


def test_inventory_poll_discovers_adaptive_lights_and_seeds_device_state():
    class FakeClient:
        async def get_devices(self):
            return [
                {
                    "id": "light-1",
                    "deviceType": "light",
                    "isReachable": True,
                    "lastSeen": "2026-07-13T07:23:47.000Z",
                    "attributes": {
                        "isOn": True,
                        "deviceOnBehavior": {"behavior": "adaptiveProfile"},
                    },
                }
            ]

    class FakeDaemon:
        def __init__(self):
            self.synced_devices = []
            self.states = []

        def sync_adaptive_lights(self, devices):
            self.synced_devices = devices

        async def handle_device_state(self, device_id, is_reachable, is_on, last_seen=None):
            self.states.append((device_id, is_reachable, is_on, last_seen))

    async def run():
        daemon = FakeDaemon()
        poll_inventory = getattr(cli, "_poll_inventory", None)

        assert poll_inventory is not None
        await poll_inventory(FakeClient(), daemon)

        assert daemon.synced_devices[0]["id"] == "light-1"
        assert daemon.states == [
            ("light-1", True, True, "2026-07-13T07:23:47.000Z")
        ]

    asyncio.run(run())


def test_initial_seed_continues_when_hub_is_unavailable():
    class OfflineClient:
        async def get_devices(self):
            raise ConnectionError("hub still starting")

    class FakeDaemon:
        async def poll_once(self):
            raise AssertionError("dynamic inventory should be used")

    async def run():
        seed_initial_state = getattr(cli, "_seed_initial_state", None)

        assert seed_initial_state is not None
        await seed_initial_state(OfflineClient(), FakeDaemon(), watch_adaptive_on_lights=True)

    asyncio.run(run())


def test_websocket_message_forwards_last_seen_to_recovery_daemon():
    class FakeDaemon:
        def __init__(self):
            self.states = []

        async def handle_device_state(self, device_id, is_reachable, is_on, last_seen=None):
            self.states.append((device_id, is_reachable, is_on, last_seen))

    async def run():
        daemon = FakeDaemon()
        handle_message = getattr(cli, "_handle_websocket_message", None)
        message = json.dumps(
            {
                "data": {
                    "id": "light-1",
                    "isReachable": True,
                    "lastSeen": "2026-07-13T07:23:47.000Z",
                }
            }
        )

        assert handle_message is not None
        await handle_message(message, daemon)

        assert daemon.states == [
            ("light-1", True, None, "2026-07-13T07:23:47.000Z")
        ]

    asyncio.run(run())
