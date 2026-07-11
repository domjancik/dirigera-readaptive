from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import yaml

from .seasonal_schedule import (
    CurveConfig,
    generate_adaptive_schedule,
    schedule_yaml_document,
    sun_times_for_date,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(), help="Date as YYYY-MM-DD.")
    parser.add_argument("--latitude", required=True, type=float)
    parser.add_argument("--longitude", required=True, type=float)
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sample-minutes", type=int, default=30)
    parser.add_argument("--sleep-time", type=float, default=21.0)
    parser.add_argument("--extend-day-after-late-sunset", action="store_true")
    parser.add_argument("--latest-sleep-time", type=float, default=23.0)
    parser.add_argument("--min-evening-ramp-hours", type=float, default=1.5)
    parser.add_argument("--min-light-level", type=int, default=10)
    parser.add_argument("--morning-light-level", type=int, default=90)
    parser.add_argument("--evening-light-level", type=int, default=90)
    parser.add_argument("--pre-sleep-light-level", type=int, default=80)
    parser.add_argument("--max-light-level", type=int, default=100)
    parser.add_argument("--warm-color-temperature", type=int, default=1000)
    parser.add_argument("--morning-color-temperature", type=int, default=2700)
    parser.add_argument("--evening-color-temperature", type=int, default=2450)
    parser.add_argument("--pre-sleep-color-temperature", type=int, default=2200)
    parser.add_argument("--cool-color-temperature", type=int, default=4600)
    parser.add_argument("--morning-transition-hours", type=float, default=2.0)
    parser.add_argument("--evening-warmup-before-sunset-hours", type=float, default=1.0)
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date)
    sun_times = sun_times_for_date(
        target_date,
        latitude=args.latitude,
        longitude=args.longitude,
        timezone_name=args.timezone,
    )
    config = CurveConfig(
        sleep_time=args.sleep_time,
        extend_day_after_late_sunset=args.extend_day_after_late_sunset,
        latest_sleep_time=args.latest_sleep_time,
        min_evening_ramp_hours=args.min_evening_ramp_hours,
        min_light_level=args.min_light_level,
        morning_light_level=args.morning_light_level,
        evening_light_level=args.evening_light_level,
        pre_sleep_light_level=args.pre_sleep_light_level,
        max_light_level=args.max_light_level,
        warm_color_temperature=args.warm_color_temperature,
        morning_color_temperature=args.morning_color_temperature,
        evening_color_temperature=args.evening_color_temperature,
        pre_sleep_color_temperature=args.pre_sleep_color_temperature,
        cool_color_temperature=args.cool_color_temperature,
        morning_transition_hours=args.morning_transition_hours,
        evening_warmup_before_sunset_hours=args.evening_warmup_before_sunset_hours,
    )
    schedule = generate_adaptive_schedule(
        sun_times,
        config,
        sample_interval_minutes=args.sample_minutes,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(schedule_yaml_document(schedule), sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(schedule)} adaptive schedule entries to {args.output}.")


if __name__ == "__main__":
    main()
