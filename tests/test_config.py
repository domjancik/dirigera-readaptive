import os
from pathlib import Path

from dirigera_readaptive.config import load_config


def test_load_config_reads_lights_and_token_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DIRIGERA_TOKEN", "secret-token")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
dirigera:
  host: 192.168.1.249
  token_env: DIRIGERA_TOKEN

lights:
  - id: light-1
    adaptive_profile_id: profile-1
    reconnect_delay_ms: 1500
    reconnect_retry_delay_ms: 750
    reconnect_attempts: 8

poll_interval_seconds: 12
activation_cooldown_seconds: 45
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.dirigera.host == "192.168.1.249"
    assert config.dirigera.token == "secret-token"
    assert config.lights[0].id == "light-1"
    assert config.lights[0].adaptive_profile_id == "profile-1"
    assert config.lights[0].reconnect_delay_ms == 1500
    assert config.lights[0].reconnect_retry_delay_ms == 750
    assert config.lights[0].reconnect_attempts == 8
    assert config.poll_interval_seconds == 12
    assert config.activation_cooldown_seconds == 45
    assert config.recover_on_reconnect is True
    assert config.recover_on_power_on is False


def test_load_config_uses_defaults_for_optional_values(tmp_path, monkeypatch):
    monkeypatch.setenv("DIRIGERA_TOKEN", "secret-token")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
dirigera:
  host: 192.168.1.249

lights:
  - id: light-1
""".strip(),
        encoding="utf-8",
    )

    config = load_config(Path(config_path))

    assert config.lights[0].adaptive_profile_id is None
    assert config.lights[0].reconnect_delay_ms == 500
    assert config.lights[0].reconnect_retry_delay_ms == 1000
    assert config.lights[0].reconnect_attempts == 12
    assert config.poll_interval_seconds == 10
    assert config.activation_cooldown_seconds == 30
    assert config.recover_on_reconnect is True
    assert config.recover_on_power_on is False


def test_load_config_allows_dynamic_adaptive_light_discovery_without_static_lights(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DIRIGERA_TOKEN", "secret-token")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
dirigera:
  host: 192.168.1.249

watch_adaptive_on_lights: true
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.lights == []
    assert config.watch_adaptive_on_lights is True


def test_load_config_reads_token_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DIRIGERA_TOKEN", raising=False)
    token_path = tmp_path / "dirigera.token"
    token_path.write_text("file-token\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
dirigera:
  host: 192.168.1.249
  token_file: {token_path}

lights:
  - id: light-1
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.dirigera.token == "file-token"


def test_load_config_rejects_missing_token(tmp_path, monkeypatch):
    monkeypatch.delenv("DIRIGERA_TOKEN", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
dirigera:
  host: 192.168.1.249

lights:
  - id: light-1
""".strip(),
        encoding="utf-8",
    )

    try:
        load_config(config_path)
    except ValueError as error:
        assert "DIRIGERA_TOKEN" in str(error)
    else:
        raise AssertionError("expected missing token error")
