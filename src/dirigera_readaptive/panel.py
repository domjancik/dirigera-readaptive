from __future__ import annotations

import argparse
import asyncio
import copy
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
import secrets
import shutil
import subprocess
from typing import Any, Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml

from .client import HttpDirigeraClient
from .config import load_dirigera_token
from .schedule_profiles import load_schedule_profiles_config, update_configured_profiles
from .seasonal_schedule import CurveConfig, generate_adaptive_schedule, sun_times_for_date


EDITABLE_CURVE_FIELDS = {
    "min_light_level",
    "morning_light_level",
    "max_light_level",
    "evening_light_level",
    "pre_sleep_light_level",
    "extend_day_after_late_sunset",
    "latest_sleep_time",
    "min_evening_ramp_hours",
}

LIGHT_LEVEL_FIELDS = {
    "min_light_level",
    "morning_light_level",
    "max_light_level",
    "evening_light_level",
    "pre_sleep_light_level",
}


class PanelService:
    def __init__(
        self,
        config_path: Path,
        status_provider: Callable[[], dict[str, Any]] | None = None,
        apply_runner: Callable[[], dict[str, bool]] | None = None,
    ) -> None:
        self._config_path = config_path
        self._status_provider = status_provider or system_status
        self._apply_runner = apply_runner or self._apply_configured_profiles

    def state(self) -> dict[str, Any]:
        return self._state_from_raw(self._read_raw_config())

    def preview_profiles(self, profiles: Any) -> dict[str, Any]:
        raw = copy.deepcopy(self._read_raw_config())
        self._update_raw_profiles(raw, profiles)
        return self._state_from_raw(raw)

    def _state_from_raw(self, raw: dict[str, Any]) -> dict[str, Any]:
        section = raw.get("schedule_updates") or {}
        if not isinstance(section, dict):
            raise ValueError("schedule_updates must be an object.")
        raw_profiles = section.get("profiles") or []
        if not isinstance(raw_profiles, list) or not raw_profiles:
            raise ValueError("schedule_updates.profiles must contain at least one profile.")
        target_date = date.fromisoformat(str(section.get("date", date.today().isoformat())))
        latitude = float(section["latitude"])
        longitude = float(section["longitude"])
        timezone = str(section["timezone"])
        sample_minutes = int(section.get("sample_minutes", 30))
        sun_times = sun_times_for_date(
            target_date,
            latitude=latitude,
            longitude=longitude,
            timezone_name=timezone,
        )
        profiles = []
        for target in raw_profiles:
            if not isinstance(target, dict):
                raise ValueError("Each configured profile must be an object.")
            raw_curve = target.get("curve") or {}
            if not isinstance(raw_curve, dict):
                raise ValueError("curve must be an object.")
            resolved_curve = CurveConfig(**raw_curve)
            curve = asdict(resolved_curve)
            profiles.append(
                {
                    "name": str(target["name"]),
                    "profileName": str(target.get("profile_name", target["name"])),
                    "curve": {name: curve[name] for name in EDITABLE_CURVE_FIELDS},
                    "preview": generate_adaptive_schedule(
                        sun_times,
                        resolved_curve,
                        sample_interval_minutes=sample_minutes,
                    ),
                }
            )
        return {
            "date": target_date.isoformat(),
            "sun": asdict(sun_times),
            "profiles": profiles,
            "system": self._status_provider(),
        }

    def save_profiles(self, profiles: Any) -> dict[str, Any]:
        raw = self._read_raw_config()
        self._update_raw_profiles(raw, profiles)
        self._write_raw_config(raw)
        return self.state()

    def apply_profiles(self, profiles: Any) -> dict[str, Any]:
        state = self.save_profiles(profiles)
        return {"state": state, "applied": self._apply_runner()}

    def _update_raw_profiles(self, raw: dict[str, Any], profiles: Any) -> None:
        if not isinstance(profiles, list):
            raise ValueError("profiles must be a list.")
        section = raw.get("schedule_updates") or {}
        configured_profiles = section.get("profiles") or []
        if not isinstance(configured_profiles, list):
            raise ValueError("schedule_updates.profiles must be a list.")

        requested_by_name = self._requested_profiles(profiles)
        configured_names = {str(profile.get("name")) for profile in configured_profiles if isinstance(profile, dict)}
        if set(requested_by_name) != configured_names:
            raise ValueError("Submitted profiles must match the configured profile names.")

        for profile in configured_profiles:
            if not isinstance(profile, dict):
                raise ValueError("Each configured profile must be an object.")
            requested_curve = requested_by_name[str(profile["name"])]
            existing_curve = profile.get("curve") or {}
            if not isinstance(existing_curve, dict):
                raise ValueError("curve must be an object.")
            effective_curve = asdict(CurveConfig())
            effective_curve.update(existing_curve)
            effective_curve.update(requested_curve)
            self._validate_curve(effective_curve)
            profile["curve"] = {**existing_curve, **requested_curve}

    def _read_raw_config(self) -> dict[str, Any]:
        raw = yaml.safe_load(self._config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("Configuration must be an object.")
        return raw

    @staticmethod
    def _requested_profiles(profiles: list[Any]) -> dict[str, dict[str, Any]]:
        requested_by_name: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            if not isinstance(profile, dict):
                raise ValueError("Each submitted profile must be an object.")
            name = profile.get("name")
            curve = profile.get("curve")
            if not isinstance(name, str) or not name:
                raise ValueError("Each submitted profile needs a name.")
            if name in requested_by_name:
                raise ValueError(f"Duplicate submitted profile {name!r}.")
            if not isinstance(curve, dict):
                raise ValueError(f"Profile {name!r} needs a curve object.")
            unknown = sorted(set(curve) - EDITABLE_CURVE_FIELDS)
            if unknown:
                raise ValueError(f"Profile {name!r} contains unknown setting(s): {', '.join(unknown)}.")
            requested_by_name[name] = curve
        return requested_by_name

    @staticmethod
    def _validate_curve(curve: dict[str, Any]) -> None:
        for field in LIGHT_LEVEL_FIELDS:
            value = curve.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100:
                raise ValueError(f"{field} must be an integer between 1 and 100.")

        if curve["min_light_level"] > min(
            curve["morning_light_level"],
            curve["max_light_level"],
            curve["evening_light_level"],
            curve["pre_sleep_light_level"],
        ):
            raise ValueError("min_light_level cannot exceed the other light levels.")
        if curve["max_light_level"] < max(
            curve["morning_light_level"],
            curve["evening_light_level"],
            curve["pre_sleep_light_level"],
        ):
            raise ValueError("max_light_level cannot be below another light level.")

        if not isinstance(curve.get("extend_day_after_late_sunset"), bool):
            raise ValueError("extend_day_after_late_sunset must be true or false.")
        latest_sleep_time = curve.get("latest_sleep_time")
        if not isinstance(latest_sleep_time, (int, float)) or isinstance(latest_sleep_time, bool):
            raise ValueError("latest_sleep_time must be a number.")
        if not 18 <= latest_sleep_time <= 23.75:
            raise ValueError("latest_sleep_time must be between 18:00 and 23:45.")

        ramp = curve.get("min_evening_ramp_hours")
        if not isinstance(ramp, (int, float)) or isinstance(ramp, bool) or not 0.25 <= ramp <= 5:
            raise ValueError("min_evening_ramp_hours must be between 0.25 and 5 hours.")

    def _write_raw_config(self, raw: dict[str, Any]) -> None:
        temporary_path = self._config_path.with_suffix(self._config_path.suffix + ".tmp")
        temporary_path.write_text(
            yaml.safe_dump(raw, sort_keys=False),
            encoding="utf-8",
        )
        temporary_path.replace(self._config_path)

    def _apply_configured_profiles(self) -> dict[str, bool]:
        raw = self._read_raw_config()
        dirigera = raw.get("dirigera") or {}
        if not isinstance(dirigera, dict):
            raise ValueError("dirigera must be an object.")
        client = HttpDirigeraClient(
            host=str(dirigera["host"]),
            token=load_dirigera_token(dirigera),
        )
        return asyncio.run(
            update_configured_profiles(client, load_schedule_profiles_config(self._config_path))
        )


def system_status() -> dict[str, Any]:
    disk = shutil.disk_usage("/")
    return {
        "units": {
            "recovery": _unit_status("dirigera-readaptive.service"),
            "scheduleTimer": _unit_status("dirigera-computed-schedule.timer"),
            "scheduleUpdate": _unit_status("dirigera-computed-schedule.service"),
            "panel": _unit_status("dirigera-panel.service"),
        },
        "disk": {
            "totalBytes": disk.total,
            "usedBytes": disk.used,
            "freeBytes": disk.free,
        },
        "journal": {"usage": _command_output(["journalctl", "--disk-usage"])},
        "firmware": {
            "temperature": _command_output(["vcgencmd", "measure_temp"]),
            "throttled": _command_output(["vcgencmd", "get_throttled"]),
        },
    }


def _unit_status(unit: str) -> dict[str, str]:
    output = _command_output(
        [
            "systemctl",
            "show",
            unit,
            "--property=ActiveState,SubState,Result,NRestarts,ActiveEnterTimestamp,NextElapseUSecRealtime",
        ]
    )
    if output.startswith("unavailable:"):
        return {"active": "unavailable"}
    values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    return {
        "active": values.get("ActiveState", "unknown"),
        "substate": values.get("SubState", "unknown"),
        "result": values.get("Result", "unknown"),
        "restarts": values.get("NRestarts", "0"),
        "since": values.get("ActiveEnterTimestamp", ""),
        "nextRun": values.get("NextElapseUSecRealtime", ""),
    }


def _command_output(command: list[str]) -> str:
    if shutil.which(command[0]) is None:
        return "unavailable: command not installed"
    try:
        result = subprocess.run(command, capture_output=True, check=False, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable: command failed"
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        return "unavailable: command failed"
    return output


class PanelHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], service: PanelService) -> None:
        super().__init__(server_address, PanelRequestHandler)
        self.service = service
        self.csrf_token = secrets.token_urlsafe(32)


class PanelRequestHandler(BaseHTTPRequestHandler):
    server: PanelHttpServer
    max_request_bytes = 1_000_000

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            document = _asset_path("panel.html").read_text(encoding="utf-8")
            self._send_bytes(
                HTTPStatus.OK,
                "text/html; charset=utf-8",
                document.replace("{{csrf_token}}", self.server.csrf_token).encode("utf-8"),
            )
            return
        if self.path in {"/panel.css", "/panel.js"}:
            content_type = "text/css; charset=utf-8" if self.path.endswith(".css") else "text/javascript; charset=utf-8"
            self._send_bytes(HTTPStatus.OK, content_type, _asset_path(self.path[1:]).read_bytes())
            return
        if self.path == "/api/state":
            self._send_json(HTTPStatus.OK, self.server.service.state())
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/api/preview", "/api/profiles", "/api/apply"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        if not secrets.compare_digest(self.headers.get("X-Panel-CSRF", ""), self.server.csrf_token):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Invalid request token."})
            return
        try:
            payload = self._read_json()
            if self.path == "/api/preview":
                state = self.server.service.preview_profiles(payload.get("profiles"))
            elif self.path == "/api/apply":
                state = self.server.service.apply_profiles(payload.get("profiles"))
            else:
                state = self.server.service.save_profiles(payload.get("profiles"))
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        except Exception:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unable to save configuration."})
            return
        self._send_json(HTTPStatus.OK, state)

    def _read_json(self) -> dict[str, Any]:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            raise ValueError("Content-Length is required.")
        try:
            length = int(content_length)
        except ValueError as error:
            raise ValueError("Content-Length must be a number.") from error
        if length < 1 or length > self.max_request_bytes:
            raise ValueError("Request body has an invalid size.")
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as error:
            raise ValueError("Request body must be valid JSON.") from error
        if not isinstance(payload, dict):
            raise ValueError("Request body must be an object.")
        return payload

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", body)

    def _send_bytes(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'none'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")

    def log_message(self, format: str, *args: Any) -> None:
        return


def _asset_path(name: str) -> Path:
    return Path(__file__).with_name(name)


def main() -> None:
    parser = argparse.ArgumentParser(description="DIRIGERA ReAdaptive local control panel")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8123, type=int)
    args = parser.parse_args()

    server = PanelHttpServer((args.host, args.port), PanelService(args.config))
    print(f"ReAdaptive panel listening at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
