from datetime import date

from dirigera_readaptive.seasonal_schedule import (
    CurveConfig,
    SunTimes,
    channels_at,
    generate_adaptive_schedule,
    get_segment_index,
    map_tween,
    schedule_entry_at,
    schedule_yaml_document,
    sun_times_for_date,
)


def test_map_tween_matches_vvvv_down_and_sine_in_out_endpoints():
    assert map_tween(4.0, 4.0, 5.0, down=False, mode="InOut") == 0.0
    assert map_tween(5.0, 4.0, 5.0, down=False, mode="InOut") == 1.0
    assert map_tween(4.0, 4.0, 5.0, down=True, mode="InOut") == 1.0
    assert map_tween(5.0, 4.0, 5.0, down=True, mode="InOut") == 0.0


def test_get_segment_index_matches_patch_break_on_first_greater_segment():
    assert get_segment_index(3.0, [-1, 5, 12, 18, 1000]) == 0
    assert get_segment_index(8.0, [-1, 5, 12, 18, 1000]) == 1
    assert get_segment_index(16.0, [-1, 5, 12, 18, 1000]) == 2
    assert get_segment_index(23.0, [-1, 5, 12, 18, 1000]) == 3


def test_channels_match_extracted_vvvv_segments():
    times = SunTimes(nautical_sunrise=4.0, sunrise=5.0, solar_noon=11.0, sunset=17.0)
    config = CurveConfig(sleep_time=21.0)

    assert channels_at(3.0, times, config).warm == 0.2
    assert channels_at(5.0, times, config).warm == 0.0
    assert channels_at(19.5, times, config).warm == 0.7
    assert channels_at(21.0, times, config).warm == 0.2

    assert channels_at(3.0, times, config).cool == 0.0
    assert channels_at(5.0, times, config).cool == 0.37
    assert channels_at(11.0, times, config).cool == 1.0
    assert channels_at(17.0, times, config).cool == 0.37
    assert channels_at(19.5, times, config).cool == 0.0


def test_schedule_entry_converts_channels_to_ikea_brightness_and_temperature():
    times = SunTimes(nautical_sunrise=4.0, sunrise=5.0, solar_noon=11.0, sunset=17.0)
    config = CurveConfig(sleep_time=21.0, max_light_level=100)

    night = schedule_entry_at(3.0, times, config)
    noon = schedule_entry_at(11.0, times, config)

    assert night == {"startTime": "03:00", "lightLevel": 10, "colorTemperature": 1000}
    assert noon == {"startTime": "11:00", "lightLevel": 100, "colorTemperature": 4600}


def test_late_sunset_does_not_turn_midnight_into_evening_peak():
    times = SunTimes(nautical_sunrise=3.0, sunrise=5.0, solar_noon=13.0, sunset=21.25)
    config = CurveConfig(sleep_time=21.0)

    assert channels_at(0.0, times, config).warm == 0.2
    assert schedule_entry_at(0.0, times, config)["lightLevel"] == 10


def test_temperature_curve_uses_smoother_ikea_like_summer_anchors():
    times = SunTimes(nautical_sunrise=3.0, sunrise=5.0, solar_noon=13.0, sunset=21.25)
    config = CurveConfig(sleep_time=21.0, extend_day_after_late_sunset=True)

    assert schedule_entry_at(5.0, times, config)["colorTemperature"] == 1000
    assert schedule_entry_at(7.0, times, config)["colorTemperature"] == 2700
    assert schedule_entry_at(13.0, times, config)["colorTemperature"] == 4600
    assert schedule_entry_at(20.25, times, config)["colorTemperature"] == 2450
    assert schedule_entry_at(21.5, times, config)["colorTemperature"] == 2200
    assert schedule_entry_at(23.0, times, config)["colorTemperature"] == 1000


def test_evening_brightness_smoothly_tapers_instead_of_post_sunset_spike():
    times = SunTimes(nautical_sunrise=3.0, sunrise=5.0, solar_noon=13.0, sunset=21.25)
    config = CurveConfig(sleep_time=21.0, extend_day_after_late_sunset=True)

    assert schedule_entry_at(20.25, times, config)["lightLevel"] == 90
    assert schedule_entry_at(21.5, times, config)["lightLevel"] == 80
    assert schedule_entry_at(22.0, times, config)["lightLevel"] < 80
    assert schedule_entry_at(23.0, times, config)["lightLevel"] == 10


def test_optional_day_extension_moves_sleep_later_for_late_sunset():
    times = SunTimes(nautical_sunrise=3.0, sunrise=5.0, solar_noon=13.0, sunset=21.25)
    config = CurveConfig(sleep_time=21.0, extend_day_after_late_sunset=True, latest_sleep_time=23.0)

    assert config.effective_sleep_time(times) == 23.0
    assert config.effective_pre_sleep_time(times) == 21.5


def test_generate_adaptive_schedule_samples_boundaries_and_regular_grid():
    times = SunTimes(nautical_sunrise=4.0, sunrise=5.0, solar_noon=11.0, sunset=17.0)
    config = CurveConfig(sleep_time=21.0)

    schedule = generate_adaptive_schedule(times, config, sample_interval_minutes=120)

    assert schedule[0]["startTime"] == "00:00"
    assert {"startTime": "04:00", "lightLevel": 10, "colorTemperature": 1000} in schedule
    assert any(entry["startTime"] == "19:30" for entry in schedule)
    assert schedule == sorted(schedule, key=lambda entry: entry["startTime"])


def test_sun_times_for_date_returns_plausible_prague_summer_local_times():
    times = sun_times_for_date(date(2024, 6, 8), latitude=50.1, longitude=14.5, timezone_name="Europe/Prague")

    assert 4.5 < times.sunrise < 5.3
    assert 20.7 < times.sunset < 21.5
    assert times.nautical_sunrise < times.sunrise < times.solar_noon < times.sunset


def test_schedule_yaml_document_wraps_entries_for_schedule_updater():
    document = schedule_yaml_document(
        [{"startTime": "11:00", "lightLevel": 100, "colorTemperature": 4600}]
    )

    assert document == {
        "adaptiveSchedule": [
            {"startTime": "11:00", "lightLevel": 100, "colorTemperature": 4600}
        ]
    }
