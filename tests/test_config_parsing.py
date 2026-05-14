from __future__ import annotations

import json
from pathlib import Path

import pytest

from voice_comms_dcs.config import ConfigError, load_config


def test_commands_example_parses_new_sections():
    config = load_config("config/commands.example.json")
    assert config.telemetry.port == 10309
    assert config.webrtc.vad_rms_threshold == 0.012
    assert config.input.poll_hz == 60
    assert config.push_to_talk.max_context_ms == 15000
    assert config.stt.cli_timeout_seconds == 30.0
    assert config.tts.piper_timeout_seconds == 30.0
    assert config.udp_reliability.protocol_version == 2
    assert config.udp_reliability.replay_window_size == 128
    assert config.dashboard_privacy.expose_position is False
    assert config.dashboard_privacy.expose_model_paths is False


def test_defaults_are_applied_when_sections_missing(tmp_path: Path):
    path = tmp_path / "commands.json"
    path.write_text(
        json.dumps(
            {
                "commands": [
                    {"id": "x", "phrases": ["x"], "action": {"type": "flag", "flag": 1}}
                ]
            }
        ),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.telemetry.host == "127.0.0.1"
    assert config.webrtc.port == 8765
    assert config.push_to_talk.max_context_ms == 15000
    assert config.udp_reliability.enabled is True
    assert config.dashboard_privacy.expose_position is False


def test_nested_stt_whisper_values_are_parsed(tmp_path: Path):
    data = json.loads(Path("config/commands.example.json").read_text(encoding="utf-8"))
    data["stt"]["whisper"]["threads"] = 9
    data["stt"]["whisper"]["cli_timeout_seconds"] = 12.5
    data["push_to_talk"]["max_context_ms"] = 22000
    path = tmp_path / "commands.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    config = load_config(path)
    assert config.stt.threads == 9
    assert config.stt.cli_timeout_seconds == 12.5
    assert config.push_to_talk.max_context_ms == 22000


def test_dashboard_privacy_and_udp_reliability_parse(tmp_path: Path):
    data = json.loads(Path("config/commands.example.json").read_text(encoding="utf-8"))
    data["udp_reliability"]["require_ack"] = True
    data["udp_reliability"]["retries"] = 2
    data["dashboard"]["privacy"]["expose_position"] = True
    data["dashboard"]["privacy"]["expose_last_transcript"] = False
    path = tmp_path / "commands.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    config = load_config(path)
    assert config.udp_reliability.require_ack is True
    assert config.udp_reliability.retries == 2
    assert config.dashboard_privacy.expose_position is True
    assert config.dashboard_privacy.expose_last_transcript is False


def test_invalid_command_definition_raises_config_error(tmp_path: Path):
    path = tmp_path / "commands.json"
    path.write_text(
        json.dumps({"commands": [{"id": "x", "phrases": ["x"], "action": {"type": "bad"}}]}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)
