from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SunTimes:
    nautical_sunrise: float
    sunrise: float
    solar_noon: float
    sunset: float


@dataclass(frozen=True)
class Channels:
    warm: float
    cool: float


@dataclass(frozen=True)
class CurveConfig:
    night_light_intensity: float = 0.2
    intense_night_light_intensity: float = 0.7
    morning_cool_level: float = 0.37
    sleep_time: float = 21.0
    pre_sleep_offset_hours: float = 1.5
    extend_day_after_late_sunset: bool = False
    latest_sleep_time: float = 23.0
    min_evening_ramp_hours: float = 1.5
    min_light_level: int = 10
    morning_light_level: int = 90
    evening_light_level: int = 90
    pre_sleep_light_level: int = 80
    max_light_level: int = 100
    warm_color_temperature: int = 1000
    morning_color_temperature: int = 2700
    evening_color_temperature: int = 2450
    pre_sleep_color_temperature: int = 2200
    cool_color_temperature: int = 4600
    morning_transition_hours: float = 2.0
    evening_warmup_before_sunset_hours: float = 1.0

    @property
    def pre_sleep_time(self) -> float:
        return self.sleep_time - self.pre_sleep_offset_hours

    def effective_sleep_time(self, sun_times: SunTimes) -> float:
        if not self.extend_day_after_late_sunset:
            return self.sleep_time
        earliest_with_evening_ramp = (
            sun_times.sunset + self.min_evening_ramp_hours + self.pre_sleep_offset_hours
        )
        return min(self.latest_sleep_time, max(self.sleep_time, earliest_with_evening_ramp))

    def effective_pre_sleep_time(self, sun_times: SunTimes) -> float:
        return self.effective_sleep_time(sun_times) - self.pre_sleep_offset_hours

    def morning_transition_end(self, sun_times: SunTimes) -> float:
        return min(sun_times.solar_noon, sun_times.sunrise + self.morning_transition_hours)

    def evening_transition_start(self, sun_times: SunTimes) -> float:
        return max(
            sun_times.solar_noon,
            sun_times.sunset - self.evening_warmup_before_sunset_hours,
        )


def map_tween(
    value: float,
    input_minimum: float,
    input_maximum: float,
    down: bool = False,
    mode: str = "In",
    output_minimum: float = 0.0,
    output_maximum: float = 1.0,
) -> float:
    if input_maximum == input_minimum:
        t = 1.0
    else:
        t = (value - input_minimum) / (input_maximum - input_minimum)
    t = _clamp(t, 0.0, 1.0)
    if down:
        t = 1.0 - t
    eased = _sine_ease(t, mode)
    return output_minimum + eased * (output_maximum - output_minimum)


def get_segment_index(value: float, segments: list[float]) -> int:
    for index, segment in enumerate(segments):
        if value < segment:
            return index - 1
    return len(segments) - 1


def channels_at(hour: float, sun_times: SunTimes, config: CurveConfig | None = None) -> Channels:
    config = config or CurveConfig()
    warm = _warm_channel(hour, sun_times, config)
    cool = _cool_channel(hour, sun_times, config)
    return Channels(warm=round(warm, 6), cool=round(cool, 6))


def schedule_entry_at(
    hour: float,
    sun_times: SunTimes,
    config: CurveConfig | None = None,
) -> dict[str, int | str]:
    config = config or CurveConfig()
    light_level = round(_light_level_at(hour, sun_times, config))
    color_temperature = round(_color_temperature_at(hour, sun_times, config))

    return {
        "startTime": _format_hour(hour),
        "lightLevel": int(_clamp(light_level, 1, 100)),
        "colorTemperature": int(color_temperature),
    }


def generate_adaptive_schedule(
    sun_times: SunTimes,
    config: CurveConfig | None = None,
    sample_interval_minutes: int = 30,
) -> list[dict[str, int | str]]:
    config = config or CurveConfig()
    hours = set()
    step_hours = sample_interval_minutes / 60
    sample_count = int(24 / step_hours)
    for index in range(sample_count):
        hours.add(round(index * step_hours, 6))
    hours.update(
        [
            0.0,
            sun_times.nautical_sunrise,
            sun_times.sunrise,
            sun_times.solar_noon,
            sun_times.sunset,
            config.morning_transition_end(sun_times),
            config.evening_transition_start(sun_times),
            config.effective_pre_sleep_time(sun_times),
            config.effective_sleep_time(sun_times),
        ]
    )

    return [
        schedule_entry_at(hour % 24, sun_times, config)
        for hour in sorted(_dedupe_minutes(hours))
        if 0 <= hour < 24
    ]


def schedule_yaml_document(schedule: list[dict[str, int | str]]) -> dict[str, list[dict[str, int | str]]]:
    return {"adaptiveSchedule": schedule}


def sun_times_for_date(
    day: date,
    latitude: float,
    longitude: float,
    timezone_name: str,
) -> SunTimes:
    zone = ZoneInfo(timezone_name)
    sunrise_utc, sunset_utc = _sunrise_sunset_utc(day, latitude, longitude, -35 / 60, True)
    nautical_sunrise_utc, _ = _sunrise_sunset_utc(day, latitude, longitude, -12.0, False)

    sunrise = _utc_hour_to_local_decimal(day, sunrise_utc, zone)
    sunset = _utc_hour_to_local_decimal(day, sunset_utc, zone)
    nautical_sunrise = _utc_hour_to_local_decimal(day, nautical_sunrise_utc, zone)
    solar_noon = (sunrise + sunset) / 2

    return SunTimes(
        nautical_sunrise=nautical_sunrise,
        sunrise=sunrise,
        solar_noon=solar_noon,
        sunset=sunset,
    )


def _light_level_at(hour: float, sun_times: SunTimes, config: CurveConfig) -> float:
    return _interpolate_anchors(
        hour,
        [
            (0.0, config.min_light_level),
            (sun_times.sunrise, config.min_light_level),
            (config.morning_transition_end(sun_times), config.morning_light_level),
            (sun_times.solar_noon, config.max_light_level),
            (config.evening_transition_start(sun_times), config.evening_light_level),
            (config.effective_pre_sleep_time(sun_times), config.pre_sleep_light_level),
            (config.effective_sleep_time(sun_times), config.min_light_level),
        ],
    )


def _color_temperature_at(hour: float, sun_times: SunTimes, config: CurveConfig) -> float:
    return _interpolate_anchors(
        hour,
        [
            (0.0, config.warm_color_temperature),
            (sun_times.sunrise, config.warm_color_temperature),
            (config.morning_transition_end(sun_times), config.morning_color_temperature),
            (sun_times.solar_noon, config.cool_color_temperature),
            (config.evening_transition_start(sun_times), config.evening_color_temperature),
            (config.effective_pre_sleep_time(sun_times), config.pre_sleep_color_temperature),
            (config.effective_sleep_time(sun_times), config.warm_color_temperature),
        ],
    )


def _warm_channel(hour: float, sun_times: SunTimes, config: CurveConfig) -> float:
    pre_sleep_time = config.effective_pre_sleep_time(sun_times)
    sleep_time = config.effective_sleep_time(sun_times)

    if hour < sun_times.sunrise:
        return map_tween(
            hour,
            sun_times.nautical_sunrise,
            sun_times.sunrise,
            down=True,
            mode="InOut",
            output_minimum=0.0,
            output_maximum=config.night_light_intensity,
        )
    if hour < sun_times.sunset:
        return 0.0
    if hour <= pre_sleep_time and pre_sleep_time > sun_times.sunset:
        return map_tween(
            hour,
            sun_times.sunset,
            pre_sleep_time,
            down=False,
            mode="InOut",
            output_minimum=0.0,
            output_maximum=config.intense_night_light_intensity,
        )
    if hour <= sleep_time and sleep_time > pre_sleep_time:
        return map_tween(
            hour,
            pre_sleep_time,
            sleep_time,
            down=True,
            mode="InOut",
            output_minimum=config.night_light_intensity,
            output_maximum=config.intense_night_light_intensity,
        )
    return config.night_light_intensity


def _cool_channel(hour: float, sun_times: SunTimes, config: CurveConfig) -> float:
    segments = [-1.0, sun_times.sunrise, sun_times.solar_noon, sun_times.sunset, 1000.0]
    segment = get_segment_index(hour, segments)
    if segment == 0:
        return map_tween(
            hour,
            sun_times.nautical_sunrise,
            sun_times.sunrise,
            down=False,
            mode="In",
            output_minimum=0.0,
            output_maximum=config.morning_cool_level,
        )
    if segment == 1:
        return map_tween(
            hour,
            sun_times.sunrise,
            sun_times.solar_noon,
            down=False,
            mode="Out",
            output_minimum=config.morning_cool_level,
            output_maximum=1.0,
        )
    if segment == 2:
        return map_tween(
            hour,
            sun_times.solar_noon,
            sun_times.sunset,
            down=True,
            mode="Out",
            output_minimum=config.morning_cool_level,
            output_maximum=1.0,
        )
    pre_sleep_time = config.effective_pre_sleep_time(sun_times)
    if hour <= pre_sleep_time and pre_sleep_time > sun_times.sunset:
        return map_tween(
            hour,
            sun_times.sunset,
            pre_sleep_time,
            down=True,
            mode="In",
            output_minimum=0.0,
            output_maximum=config.morning_cool_level,
        )
    return 0.0


def _sine_ease(value: float, mode: str) -> float:
    mode_normalized = mode.lower()
    if mode_normalized == "in":
        return 1 - math.cos((value * math.pi) / 2)
    if mode_normalized == "out":
        return math.sin((value * math.pi) / 2)
    if mode_normalized == "inout":
        return -(math.cos(math.pi * value) - 1) / 2
    raise ValueError(f"Unsupported tween mode: {mode}")


def _interpolate_anchors(hour: float, anchors: list[tuple[float, float]]) -> float:
    ordered = _ordered_anchors(anchors)
    if not ordered:
        raise ValueError("At least one anchor is required.")
    if hour <= ordered[0][0]:
        return ordered[0][1]

    previous_hour, previous_value = ordered[0]
    for next_hour, next_value in ordered[1:]:
        if hour <= next_hour:
            return map_tween(
                hour,
                previous_hour,
                next_hour,
                mode="InOut",
                output_minimum=previous_value,
                output_maximum=next_value,
            )
        previous_hour = next_hour
        previous_value = next_value
    return ordered[-1][1]


def _ordered_anchors(anchors: list[tuple[float, float]]) -> list[tuple[float, float]]:
    by_minute: dict[int, float] = {}
    for hour, value in anchors:
        if 0 <= hour < 24:
            by_minute[round(hour * 60)] = value
    return [(minute / 60, value) for minute, value in sorted(by_minute.items())]


def _format_hour(hour: float) -> str:
    total_minutes = round((hour % 24) * 60)
    total_minutes %= 24 * 60
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _dedupe_minutes(hours: set[float]) -> list[float]:
    minute_values = sorted({round((hour % 24) * 60) % (24 * 60) for hour in hours})
    return [minutes / 60 for minutes in minute_values]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


# Port of Paul Schlyter's sunriset.c as used by the old ZdraveSvetlo project.
def _sunrise_sunset_utc(
    day: date,
    latitude: float,
    longitude: float,
    altitude: float,
    upper_limb: bool,
) -> tuple[float, float]:
    d = _days_since_2000_jan_0(day.year, day.month, day.day) + 0.5 - longitude / 360.0
    sidtime = _revolution(_gmst0(d) + 180.0 + longitude)
    sun_ra, sun_declination, sun_distance = _sun_ra_dec(d)
    south_time = 12.0 - _rev180(sidtime - sun_ra) / 15.0
    sun_radius = 0.2666 / sun_distance
    if upper_limb:
        altitude -= sun_radius

    cost = (
        _sind(altitude)
        - _sind(latitude) * _sind(sun_declination)
    ) / (_cosd(latitude) * _cosd(sun_declination))
    if cost >= 1.0:
        arc = 0.0
    elif cost <= -1.0:
        arc = 12.0
    else:
        arc = _acosd(cost) / 15.0

    return south_time - arc, south_time + arc


def _utc_hour_to_local_decimal(day: date, utc_hour: float, zone: ZoneInfo) -> float:
    utc_midnight = datetime.combine(day, time(), tzinfo=timezone.utc)
    moment = utc_midnight + timedelta(hours=utc_hour)
    local = moment.astimezone(zone)
    return local.hour + local.minute / 60 + local.second / 3600


def _days_since_2000_jan_0(year: int, month: int, day: int) -> int:
    return (
        367 * year
        - ((7 * (year + ((month + 9) // 12))) // 4)
        + ((275 * month) // 9)
        + day
        - 730530
    )


RAD_DEG = 180.0 / math.pi
DEG_RAD = math.pi / 180.0


def _sind(value: float) -> float:
    return math.sin(value * DEG_RAD)


def _cosd(value: float) -> float:
    return math.cos(value * DEG_RAD)


def _atan2d(y: float, x: float) -> float:
    return RAD_DEG * math.atan2(y, x)


def _acosd(value: float) -> float:
    return RAD_DEG * math.acos(value)


def _sunpos(d: float) -> tuple[float, float]:
    mean_anomaly = _revolution(356.0470 + 0.9856002585 * d)
    perihelion = 282.9404 + 4.70935e-5 * d
    eccentricity = 0.016709 - 1.151e-9 * d
    eccentric_anomaly = (
        mean_anomaly
        + eccentricity * RAD_DEG * _sind(mean_anomaly) * (1.0 + eccentricity * _cosd(mean_anomaly))
    )
    x = _cosd(eccentric_anomaly) - eccentricity
    y = math.sqrt(1.0 - eccentricity * eccentricity) * _sind(eccentric_anomaly)
    distance = math.sqrt(x * x + y * y)
    true_anomaly = _atan2d(y, x)
    longitude = true_anomaly + perihelion
    if longitude >= 360.0:
        longitude -= 360.0
    return longitude, distance


def _sun_ra_dec(d: float) -> tuple[float, float, float]:
    longitude, distance = _sunpos(d)
    obliquity = 23.4393 - 3.563e-7 * d
    x = distance * _cosd(longitude)
    y = distance * _sind(longitude)
    z = y * _sind(obliquity)
    y = y * _cosd(obliquity)
    right_ascension = _atan2d(y, x)
    declination = _atan2d(z, math.sqrt(x * x + y * y))
    return right_ascension, declination, distance


def _revolution(value: float) -> float:
    return value - 360.0 * math.floor(value / 360.0)


def _rev180(value: float) -> float:
    return value - 360.0 * math.floor(value / 360.0 + 0.5)


def _gmst0(d: float) -> float:
    return _revolution((180.0 + 356.0470 + 282.9404) + (0.9856002585 + 4.70935e-5) * d)
