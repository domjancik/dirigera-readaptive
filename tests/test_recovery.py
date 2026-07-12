import asyncio
import logging
from collections import defaultdict

from dirigera_readaptive.recovery import LightConfig, RecoveryDaemon


class FakeClient:
    def __init__(self, devices):
        self.devices = devices
        self.activations = []
        self.reads = defaultdict(int)
        self.failures_before_success = 0

    async def get_device(self, device_id):
        self.reads[device_id] += 1
        return self.devices[device_id]

    async def activate_adaptive(self, device_id, profile_id):
        if self.failures_before_success:
            self.failures_before_success -= 1
            raise RuntimeError("not ready")
        self.activations.append((device_id, profile_id))


def test_reachable_transition_reactivates_native_adaptive_for_on_light():
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": True},
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[LightConfig(id="light-1", adaptive_profile_id="profile-1", reconnect_delay_ms=0)],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

        assert client.activations == [("light-1", "profile-1")]

    asyncio.run(run())


def test_recovery_writes_activation_to_journal_log(caplog):
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": True},
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[LightConfig(id="light-1", adaptive_profile_id="profile-1", reconnect_delay_ms=0)],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

    caplog.set_level(logging.INFO, logger="dirigera_readaptive.recovery")
    asyncio.run(run())

    assert "Adaptive recovery activated device=light-1 profile=profile-1 attempt=1" in caplog.text


def test_recovery_logs_when_light_never_becomes_ready(caplog):
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": False},
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[
                LightConfig(
                    id="light-1",
                    adaptive_profile_id="profile-1",
                    reconnect_delay_ms=0,
                    reconnect_attempts=1,
                )
            ],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

    caplog.set_level(logging.INFO, logger="dirigera_readaptive.recovery")
    asyncio.run(run())

    assert "Adaptive recovery skipped device=light-1 reason=not-ready attempts=1" in caplog.text


def test_power_on_transition_is_disabled_by_default():
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": True},
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[LightConfig(id="light-1", adaptive_profile_id="profile-1", reconnect_delay_ms=0)],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )

        await daemon.handle_device_state("light-1", is_reachable=True, is_on=False)
        await daemon.handle_device_state("light-1", is_reachable=True, is_on=True)

        assert client.activations == []

    asyncio.run(run())


def test_reconnect_transition_can_be_disabled():
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": True},
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[LightConfig(id="light-1", adaptive_profile_id="profile-1", reconnect_delay_ms=0)],
            cooldown_seconds=30,
            recover_on_reconnect=False,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

        assert client.activations == []

    asyncio.run(run())


def test_reachable_transition_does_not_turn_on_off_light():
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": False},
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[LightConfig(id="light-1", adaptive_profile_id="profile-1", reconnect_delay_ms=0)],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

        assert client.activations == []

    asyncio.run(run())


def test_reconnect_waits_for_light_to_finish_settling_before_activating():
    class SettlingClient(FakeClient):
        def __init__(self):
            super().__init__({})
            self.states = [
                {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": False},
                    "adaptiveProfile": {},
                },
                {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": True},
                    "adaptiveProfile": {},
                },
            ]

        async def get_device(self, device_id):
            self.reads[device_id] += 1
            return self.states.pop(0)

    async def run():
        client = SettlingClient()
        sleeps = []

        async def sleep(seconds):
            sleeps.append(seconds)

        daemon = RecoveryDaemon(
            client=client,
            lights=[
                LightConfig(
                    id="light-1",
                    adaptive_profile_id="profile-1",
                    reconnect_delay_ms=0,
                    reconnect_retry_delay_ms=0,
                    reconnect_attempts=2,
                )
            ],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=sleep,
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

        assert client.activations == [("light-1", "profile-1")]
        assert client.reads["light-1"] == 2
        assert sleeps == [0, 0]

    asyncio.run(run())


def test_profile_id_can_be_discovered_from_device_on_behavior_without_mutating_it():
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {
                        "isOn": True,
                        "deviceOnBehavior": {
                            "behavior": "adaptiveProfile",
                            "profileId": "profile-from-hub",
                        },
                    },
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[LightConfig(id="light-1", reconnect_delay_ms=0)],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

        assert client.activations == [("light-1", "profile-from-hub")]

    asyncio.run(run())


def test_device_on_behavior_profile_is_preferred_over_current_active_profile():
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {
                        "isOn": True,
                        "deviceOnBehavior": {
                            "behavior": "adaptiveProfile",
                            "profileId": "profile-from-turn-on-setting",
                        },
                    },
                    "adaptiveProfile": {
                        "id": "profile-from-current-state",
                        "active": True,
                    },
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[LightConfig(id="light-1", reconnect_delay_ms=0)],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

        assert client.activations == [("light-1", "profile-from-turn-on-setting")]

    asyncio.run(run())


def test_cooldown_prevents_duplicate_activation():
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": True},
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[LightConfig(id="light-1", adaptive_profile_id="profile-1", reconnect_delay_ms=0)],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)
        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

        assert client.activations == [("light-1", "profile-1")]

    asyncio.run(run())


def test_power_on_transition_reactivates_native_adaptive():
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": True},
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[LightConfig(id="light-1", adaptive_profile_id="profile-1", reconnect_delay_ms=0)],
            cooldown_seconds=30,
            recover_on_power_on=True,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )

        await daemon.handle_device_state("light-1", is_reachable=True, is_on=False)
        await daemon.handle_device_state("light-1", is_reachable=True, is_on=True)

        assert client.activations == [("light-1", "profile-1")]

    asyncio.run(run())


def test_activation_retries_with_bounded_backoff():
    async def run():
        client = FakeClient(
            {
                "light-1": {
                    "id": "light-1",
                    "isReachable": True,
                    "attributes": {"isOn": True},
                    "adaptiveProfile": {},
                }
            }
        )
        client.failures_before_success = 2
        sleeps = []

        async def sleep(seconds):
            sleeps.append(seconds)

        daemon = RecoveryDaemon(
            client=client,
            lights=[LightConfig(id="light-1", adaptive_profile_id="profile-1", reconnect_delay_ms=0)],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=sleep,
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

        assert client.activations == [("light-1", "profile-1")]
        assert sleeps == [0, 0.5, 1.0]

    asyncio.run(run())
