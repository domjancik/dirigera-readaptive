import asyncio

from dirigera_readaptive import cli


def test_inventory_poll_discovers_adaptive_lights_and_seeds_device_state():
    class FakeClient:
        async def get_devices(self):
            return [
                {
                    "id": "light-1",
                    "deviceType": "light",
                    "isReachable": True,
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

        async def handle_device_state(self, device_id, is_reachable, is_on):
            self.states.append((device_id, is_reachable, is_on))

    async def run():
        daemon = FakeDaemon()
        poll_inventory = getattr(cli, "_poll_inventory", None)

        assert poll_inventory is not None
        await poll_inventory(FakeClient(), daemon)

        assert daemon.synced_devices[0]["id"] == "light-1"
        assert daemon.states == [("light-1", True, True)]

    asyncio.run(run())
