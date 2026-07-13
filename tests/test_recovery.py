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


def test_heartbeat_last_seen_does_not_reactivate_adaptive():
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

        await daemon.handle_device_state(
            "light-1",
            is_reachable=True,
            is_on=True,
            last_seen="2026-07-13T07:20:00.000Z",
        )
        await daemon.handle_device_state(
            "light-1",
            is_reachable=True,
            is_on=True,
            last_seen="2026-07-13T07:23:47.000Z",
        )

        assert client.activations == []

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


def test_discovery_adds_every_light_with_an_adaptive_on_behavior():
    async def run():
        client = FakeClient(
            {
                "adaptive-light": {
                    "id": "adaptive-light",
                    "isReachable": True,
                    "attributes": {
                        "isOn": True,
                        "deviceOnBehavior": {
                            "behavior": "adaptiveProfile",
                            "profileId": "profile-1",
                        },
                    },
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )
        daemon.sync_adaptive_lights(
            [
                {
                    "id": "adaptive-light",
                    "deviceType": "light",
                    "attributes": {
                        "deviceOnBehavior": {"behavior": "adaptiveProfile"}
                    },
                },
                {
                    "id": "manual-light",
                    "deviceType": "light",
                    "attributes": {
                        "deviceOnBehavior": {"behavior": "lastState"}
                    },
                },
                {
                    "id": "adaptive-sensor",
                    "deviceType": "motionSensor",
                    "attributes": {
                        "deviceOnBehavior": {"behavior": "adaptiveProfile"}
                    },
                },
            ]
        )

        await daemon.handle_reachability("adaptive-light", False)
        await daemon.handle_reachability("adaptive-light", True)
        await daemon.handle_reachability("manual-light", False)
        await daemon.handle_reachability("manual-light", True)

        assert client.activations == [("adaptive-light", "profile-1")]

    asyncio.run(run())


def test_discovery_stops_watching_a_light_when_adaptive_on_behavior_is_removed():
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
                            "profileId": "profile-1",
                        },
                    },
                    "adaptiveProfile": {},
                }
            }
        )
        daemon = RecoveryDaemon(
            client=client,
            lights=[],
            cooldown_seconds=30,
            now=lambda: 100.0,
            sleep=lambda _: asyncio.sleep(0),
        )
        daemon.sync_adaptive_lights(
            [
                {
                    "id": "light-1",
                    "deviceType": "light",
                    "attributes": {
                        "deviceOnBehavior": {"behavior": "adaptiveProfile"}
                    },
                }
            ]
        )
        daemon.sync_adaptive_lights(
            [
                {
                    "id": "light-1",
                    "deviceType": "light",
                    "attributes": {
                        "deviceOnBehavior": {"behavior": "lastState"}
                    },
                }
            ]
        )

        await daemon.handle_reachability("light-1", False)
        await daemon.handle_reachability("light-1", True)

        assert client.activations == []

    asyncio.run(run())


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
