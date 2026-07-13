import json
import threading
from urllib.request import Request, urlopen

import yaml

from dirigera_readaptive.panel import PanelHttpServer, PanelService


def test_panel_saves_curve_settings_and_returns_a_new_schedule_preview(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
dirigera:
  host: 192.0.2.20
  token_file: /private/token
schedule_updates:
  date: 2026-07-13
  latitude: 50.1
  longitude: 14.5
  timezone: Europe/Prague
  profiles:
    - name: standard
      profile_name: ReAdaptive
      curve:
        min_light_level: 10
        max_light_level: 100
        extend_day_after_late_sunset: true
    - name: dimmed
      profile_name: ReAdaptive Dimmed
      curve:
        min_light_level: 4
        morning_light_level: 70
        max_light_level: 85
        evening_light_level: 47
        pre_sleep_light_level: 42
        extend_day_after_late_sunset: true
""".strip(),
        encoding="utf-8",
    )
    panel = PanelService(config_path)

    state = panel.state()
    updated = panel.save_profiles(
        [
            {
                "name": "standard",
                "curve": {
                    "min_light_level": 8,
                    "morning_light_level": 82,
                    "max_light_level": 92,
                    "evening_light_level": 60,
                    "pre_sleep_light_level": 45,
                    "extend_day_after_late_sunset": False,
                    "latest_sleep_time": 22.5,
                },
            },
            state["profiles"][1],
        ]
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    curve = saved["schedule_updates"]["profiles"][0]["curve"]
    assert curve["min_light_level"] == 8
    assert curve["max_light_level"] == 92
    assert curve["extend_day_after_late_sunset"] is False
    assert updated["profiles"][0]["preview"][0]["lightLevel"] == 8
    assert "token_file" not in updated


def test_panel_http_api_returns_profile_state_without_sensitive_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
dirigera:
  host: 192.0.2.20
  token_file: /private/token
schedule_updates:
  latitude: 50.1
  longitude: 14.5
  timezone: Europe/Prague
  profiles:
    - name: standard
      profile_name: ReAdaptive
      curve: {}
""".strip(),
        encoding="utf-8",
    )
    server = PanelHttpServer(("127.0.0.1", 0), PanelService(config_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/api/state") as response:
            payload = json.load(response)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert payload["profiles"][0]["name"] == "standard"
    assert "token_file" not in payload
    assert "dirigera" not in payload


def test_panel_serves_the_control_surface_with_a_csrf_token(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
schedule_updates:
  latitude: 50.1
  longitude: 14.5
  timezone: Europe/Prague
  profiles:
    - name: standard
      curve: {}
""".strip(),
        encoding="utf-8",
    )
    server = PanelHttpServer(("127.0.0.1", 0), PanelService(config_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
            document = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert "<title>ReAdaptive Control</title>" in document
    assert 'name="panel-csrf"' in document


def test_panel_includes_injected_system_status_in_state(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
schedule_updates:
  latitude: 50.1
  longitude: 14.5
  timezone: Europe/Prague
  profiles:
    - name: standard
      curve: {}
""".strip(),
        encoding="utf-8",
    )
    panel = PanelService(
        config_path,
        status_provider=lambda: {
            "units": {"recovery": {"active": "active"}},
            "disk": {"freeBytes": 10},
        },
    )

    assert panel.state()["system"] == {
        "units": {"recovery": {"active": "active"}},
        "disk": {"freeBytes": 10},
    }


def test_panel_previews_curve_changes_without_writing_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    original = """
schedule_updates:
  date: 2026-07-13
  latitude: 50.1
  longitude: 14.5
  timezone: Europe/Prague
  profiles:
    - name: standard
      curve: {}
""".strip()
    config_path.write_text(original, encoding="utf-8")
    panel = PanelService(config_path, status_provider=lambda: {})
    state = panel.state()

    preview = panel.preview_profiles(
        [
            {
                "name": "standard",
                "curve": {**state["profiles"][0]["curve"], "max_light_level": 96},
            }
        ]
    )

    assert max(item["lightLevel"] for item in preview["profiles"][0]["preview"]) == 96
    assert config_path.read_text(encoding="utf-8") == original


def test_panel_http_preview_returns_an_unsaved_schedule(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
schedule_updates:
  latitude: 50.1
  longitude: 14.5
  timezone: Europe/Prague
  profiles:
    - name: standard
      curve: {}
""".strip(),
        encoding="utf-8",
    )
    server = PanelHttpServer(("127.0.0.1", 0), PanelService(config_path, status_provider=lambda: {}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/preview",
            data=json.dumps(
                {
                    "profiles": [
                        {
                            "name": "standard",
                            "curve": {
                                "min_light_level": 10,
                                "morning_light_level": 90,
                                "max_light_level": 96,
                                "evening_light_level": 55,
                                "pre_sleep_light_level": 50,
                                "extend_day_after_late_sunset": False,
                                "latest_sleep_time": 23,
                                "min_evening_ramp_hours": 1.5,
                            },
                        }
                    ]
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Panel-CSRF": server.csrf_token},
            method="POST",
        )
        with urlopen(request) as response:
            preview = json.load(response)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert max(item["lightLevel"] for item in preview["profiles"][0]["preview"]) == 96


def test_panel_apply_saves_configuration_then_runs_profile_update(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
schedule_updates:
  latitude: 50.1
  longitude: 14.5
  timezone: Europe/Prague
  profiles:
    - name: standard
      curve: {}
""".strip(),
        encoding="utf-8",
    )
    calls = []
    panel = PanelService(
        config_path,
        status_provider=lambda: {},
        apply_runner=lambda: calls.append("applied") or {"standard": True},
    )
    profile = panel.state()["profiles"][0]

    result = panel.apply_profiles(
        [{"name": "standard", "curve": {**profile["curve"], "max_light_level": 96}}]
    )

    assert calls == ["applied"]
    assert result["applied"] == {"standard": True}
    assert max(item["lightLevel"] for item in result["state"]["profiles"][0]["preview"]) == 96
