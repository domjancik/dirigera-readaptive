import asyncio

from dirigera_readaptive.schedule_update import (
    build_profile_update,
    load_schedule_file,
    update_profile_if_changed,
)


class FakeProfileClient:
    def __init__(self, home):
        self.home = home
        self.updates = []

    async def get_home(self):
        return self.home

    async def update_adaptive_profile(self, profile_id, profile):
        self.updates.append((profile_id, profile))


def test_build_profile_update_preserves_id_and_name_replacing_schedule():
    current = {
        "id": "profile-1",
        "name": "Computed schedule",
        "adaptiveSchedule": [{"startTime": "00:00", "lightLevel": 10, "colorTemperature": 1000}],
    }
    schedule = [{"startTime": "20:00", "lightLevel": 81, "colorTemperature": 2000}]

    assert build_profile_update(current, schedule) == {
        "id": "profile-1",
        "name": "Computed schedule",
        "adaptiveSchedule": schedule,
    }


def test_update_profile_if_changed_puts_new_schedule():
    async def run():
        client = FakeProfileClient(
            {
                "adaptiveProfiles": [
                    {
                        "id": "profile-1",
                        "name": "Computed schedule",
                        "adaptiveSchedule": [
                            {"startTime": "00:00", "lightLevel": 10, "colorTemperature": 1000}
                        ],
                    }
                ]
            }
        )
        schedule = [{"startTime": "20:00", "lightLevel": 81, "colorTemperature": 2000}]

        changed = await update_profile_if_changed(client, "profile-1", schedule)

        assert changed is True
        assert client.updates == [
            (
                "profile-1",
                {
                    "id": "profile-1",
                    "name": "Computed schedule",
                    "adaptiveSchedule": schedule,
                },
            )
        ]

    asyncio.run(run())


def test_update_profile_if_changed_skips_identical_schedule():
    async def run():
        schedule = [{"startTime": "20:00", "lightLevel": 81, "colorTemperature": 2000}]
        client = FakeProfileClient(
            {
                "adaptiveProfiles": [
                    {
                        "id": "profile-1",
                        "name": "Computed schedule",
                        "adaptiveSchedule": schedule,
                    }
                ]
            }
        )

        changed = await update_profile_if_changed(client, "profile-1", schedule)

        assert changed is False
        assert client.updates == []

    asyncio.run(run())


def test_load_schedule_file_reads_adaptive_schedule(tmp_path):
    path = tmp_path / "schedule.yaml"
    path.write_text(
        """
adaptiveSchedule:
  - startTime: "06:00"
    lightLevel: 20
    colorTemperature: 2200
""".strip(),
        encoding="utf-8",
    )

    assert load_schedule_file(path) == [
        {"startTime": "06:00", "lightLevel": 20, "colorTemperature": 2200}
    ]
