import asyncio

from dirigera_readaptive.schedule_profiles import (
    load_schedule_profiles_config,
    update_configured_profiles,
)


class FakeProfileClient:
    def __init__(self):
        self.home = {
            "adaptiveProfiles": [
                {
                    "id": "standard-profile",
                    "name": "Computed schedule",
                    "adaptiveSchedule": [],
                },
                {
                    "id": "dimmed-profile",
                    "name": "Computed schedule dimmed",
                    "adaptiveSchedule": [],
                },
            ]
        }
        self.updates = []

    async def get_home(self):
        return self.home

    async def update_adaptive_profile(self, profile_id, profile):
        self.updates.append((profile_id, profile))
        for current in self.home["adaptiveProfiles"]:
            if current["id"] == profile_id:
                current["adaptiveSchedule"] = profile["adaptiveSchedule"]


def test_configured_profiles_are_generated_written_and_applied(tmp_path):
    config_path = tmp_path / "config.yaml"
    standard_output = tmp_path / "computed.yaml"
    dimmed_output = tmp_path / "computed-dim.yaml"
    config_path.write_text(
        f"""
schedule_updates:
  date: 2024-06-08
  latitude: 50.1
  longitude: 14.5
  timezone: Europe/Prague
  profiles:
    - name: standard
      profile_id: standard-profile
      output: {standard_output}
      curve:
        extend_day_after_late_sunset: true
    - name: dimmed
      profile_id: dimmed-profile
      output: {dimmed_output}
      curve:
        extend_day_after_late_sunset: true
        min_light_level: 4
        morning_light_level: 70
        max_light_level: 85
        evening_light_level: 75
        pre_sleep_light_level: 65
""".strip(),
        encoding="utf-8",
    )
    client = FakeProfileClient()

    result = asyncio.run(update_configured_profiles(client, load_schedule_profiles_config(config_path)))

    assert result == {"standard": True, "dimmed": True}
    assert [profile_id for profile_id, _ in client.updates] == ["standard-profile", "dimmed-profile"]
    assert standard_output.exists()
    assert dimmed_output.exists()
    standard_schedule = client.updates[0][1]["adaptiveSchedule"]
    dimmed_schedule = client.updates[1][1]["adaptiveSchedule"]
    assert standard_schedule[0] == {
        "startTime": "00:00",
        "lightLevel": 10,
        "colorTemperature": 1000,
    }
    assert dimmed_schedule[0] == {
        "startTime": "00:00",
        "lightLevel": 4,
        "colorTemperature": 1000,
    }
    assert max(entry["lightLevel"] for entry in dimmed_schedule) == 85


def test_configured_profiles_skip_unchanged_schedules(tmp_path):
    config_path = tmp_path / "config.yaml"
    output_path = tmp_path / "computed.yaml"
    config_path.write_text(
        f"""
schedule_updates:
  date: 2024-06-08
  latitude: 50.1
  longitude: 14.5
  timezone: Europe/Prague
  profiles:
    - name: standard
      profile_id: standard-profile
      output: {output_path}
      curve:
        extend_day_after_late_sunset: true
""".strip(),
        encoding="utf-8",
    )
    config = load_schedule_profiles_config(config_path)
    client = FakeProfileClient()

    first = asyncio.run(update_configured_profiles(client, config))
    second = asyncio.run(update_configured_profiles(client, config))

    assert first == {"standard": True}
    assert second == {"standard": False}
    assert len(client.updates) == 1
