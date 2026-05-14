from __future__ import annotations

import json

import pytest

from voice_comms_dcs.config import ConfigError, load_config
from voice_comms_dcs.runtime_config import ensure_default_config, ensure_user_config


def _minimal_config() -> dict[str, object]:
    return {
        "commands": [
            {
                "id": "request_tanker",
                "phrases": ["request tanker"],
                "action": {"type": "flag", "flag": 5101, "value": 1},
            }
        ]
    }


def test_default_config_created_from_example_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    template = config_dir / "commands.example.json"
    template.write_text(json.dumps(_minimal_config()), encoding="utf-8")

    config = load_config(ensure_default_config("config/commands.json"))

    created = config_dir / "commands.json"
    assert created.exists()
    assert config.commands[0].id == "request_tanker"


def test_ensure_user_config_does_not_overwrite_existing_file(tmp_path):
    config_path = tmp_path / "commands.json"
    template_path = tmp_path / "commands.example.json"
    config_path.write_text('{"existing": true}', encoding="utf-8")
    template_path.write_text('{"template": true}', encoding="utf-8")

    assert ensure_user_config(config_path, template_path) == config_path
    assert config_path.read_text(encoding="utf-8") == '{"existing": true}'


def test_explicit_missing_config_path_still_raises(tmp_path):
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(tmp_path / "missing.json")
