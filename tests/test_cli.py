import asyncio
import json

from dirigera_readaptive import cli


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
