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


def test_invalid_command_definition_raises_config_error(tmp_path: Path):
    path = tmp_path / "commands.json"
    path.write_text(
        json.dumps({"commands": [{"id": "x", "phrases": ["x"], "action": {"type": "bad"}}]}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)
