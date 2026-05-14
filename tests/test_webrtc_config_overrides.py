from __future__ import annotations

import json
from pathlib import Path

from voice_comms_dcs.config import load_config, resolve_bridge_runtime_config


def test_config_values_used_when_cli_omitted(tmp_path: Path):
    data = json.loads(Path("config/commands.example.json").read_text(encoding="utf-8"))
    data["webrtc"]["host"] = "127.0.0.2"
    data["webrtc"]["port"] = 9999
    data["telemetry"]["port"] = 10444
    data["push_to_talk"]["pre_roll_ms"] = 750
    data["push_to_talk"]["max_context_ms"] = 12000
    path = tmp_path / "commands.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    runtime = resolve_bridge_runtime_config(load_config(path))
    assert runtime.host == "127.0.0.2"
    assert runtime.port == 9999
    assert runtime.telemetry_port == 10444
    assert runtime.pre_roll_ms == 750
    assert runtime.max_context_ms == 12000


def test_cli_values_override_config():
    runtime = resolve_bridge_runtime_config(
        load_config("config/commands.example.json"),
        host="0.0.0.0",
        port=9000,
        telemetry_host="127.0.0.9",
        telemetry_port=12345,
        ptt_hotkey="space",
        joystick_index=2,
        joystick_button=3,
    )
    assert runtime.host == "0.0.0.0"
    assert runtime.port == 9000
    assert runtime.telemetry_host == "127.0.0.9"
    assert runtime.telemetry_port == 12345
    assert runtime.ptt_hotkey == "space"
    assert runtime.joystick_index == 2
    assert runtime.joystick_button == 3


def test_disable_input_manager_overrides_config():
    runtime = resolve_bridge_runtime_config(load_config("config/commands.example.json"), enable_input_manager=False)
    assert runtime.keyboard_enabled is False
    assert runtime.joystick_enabled is False
