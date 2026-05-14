from __future__ import annotations

from pathlib import Path


def test_pyinstaller_uses_example_config_not_local_config():
    spec = Path("build/pyinstaller.spec").read_text(encoding="utf-8")
    assert '"commands.example.json"' in spec
    assert '"commands.json"' not in spec
    assert "setup_whisper.ps1" not in spec
    assert "setup_local_models.ps1" not in spec
    assert "sign_release.ps1" not in spec


def test_inno_installer_does_not_install_local_commands_json():
    iss = Path("build/voice-comms-dcs.iss").read_text(encoding="utf-8")
    assert 'Source: "..\\config\\commands.example.json"' in iss
    assert 'Source: "..\\config\\commands.json"' not in iss


def test_inno_lua_install_is_opt_in_and_gated_by_task():
    iss = Path("build/voice-comms-dcs.iss").read_text(encoding="utf-8")
    task_lines = [line for line in iss.splitlines() if 'Name: "installlua"' in line]
    assert len(task_lines) == 1
    assert "unchecked" in task_lines[0]
    assert "checkedonce" not in task_lines[0]
    assert "Tasks: installlua" in iss
    assert "--install-lua" in iss
