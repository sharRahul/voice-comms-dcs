from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from voice_comms_dcs import srs_audio
from voice_comms_dcs.srs_audio import SrsAudioConfig, SrsExternalAudioAdapter


def test_fixed_command_generation_uses_safe_default_template(tmp_path: Path) -> None:
    exe = tmp_path / "DCS-SR-ExternalAudio.exe"
    config = SrsAudioConfig(external_audio_exe=str(exe), frequency_mhz=251.0, modulation="AM", coalition="blue")
    command = SrsExternalAudioAdapter(config)._build_command(tmp_path / "radio.wav")

    assert command == [
        str(exe),
        "--file",
        str(tmp_path / "radio.wav"),
        "--freq",
        "251.000",
        "--modulation",
        "AM",
        "--coalition",
        "blue",
    ]


def test_unsafe_command_template_ignored_when_not_explicitly_allowed(tmp_path: Path, caplog) -> None:
    config_path = tmp_path / "srs_audio.json"
    exe = tmp_path / "DCS-SR-ExternalAudio.exe"
    config_path.write_text(
        json.dumps(
            {
                "enabled": False,
                "external_audio_exe": str(exe),
                "command_template": ["powershell.exe", "-Command", "Remove-Item"],
            }
        ),
        encoding="utf-8",
    )

    adapter = SrsExternalAudioAdapter.from_json(config_path)

    assert adapter.config.command_template is None
    assert adapter._build_command(tmp_path / "radio.wav")[0] == str(exe)
    assert "Ignoring SRS command_template" in caplog.text


def test_invalid_custom_template_rejected_when_enabled(tmp_path: Path) -> None:
    exe = tmp_path / "DCS-SR-ExternalAudio.exe"

    with pytest.raises(ValueError, match="first token"):
        SrsAudioConfig(
            external_audio_exe=str(exe),
            allow_custom_command_template=True,
            command_template=["powershell.exe", "-Command", "Write-Host bad"],
        )


def test_blocked_external_audio_executable_is_rejected() -> None:
    with pytest.raises(ValueError, match="blocked"):
        SrsAudioConfig(external_audio_exe="cmd.exe")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"frequency_mhz": 0.5}, "frequency_mhz"),
        ({"frequency_mhz": 1001.0}, "frequency_mhz"),
        ({"modulation": "USB"}, "modulation"),
        ({"coalition": "green"}, "coalition"),
    ],
)
def test_invalid_frequency_modulation_and_coalition_rejected(
    tmp_path: Path,
    kwargs: dict[str, object],
    message: str,
) -> None:
    exe = tmp_path / "DCS-SR-ExternalAudio.exe"
    with pytest.raises(ValueError, match=message):
        SrsAudioConfig(external_audio_exe=str(exe), **kwargs)


def test_dispatch_uses_subprocess_shell_false_and_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe = tmp_path / "DCS-SR-ExternalAudio.exe"
    exe.write_text("stub", encoding="utf-8")
    wav = tmp_path / "input.wav"
    wav.write_bytes(b"RIFF")
    output_dir = tmp_path / "out"
    calls: dict[str, object] = {}

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command: list[str], **kwargs: object) -> Completed:
        calls["command"] = command
        calls.update(kwargs)
        return Completed()

    monkeypatch.setattr(srs_audio.subprocess, "run", fake_run)
    adapter = SrsExternalAudioAdapter(
        SrsAudioConfig(
            enabled=True,
            external_audio_exe=str(exe),
            output_dir=str(output_dir),
            timeout_seconds=3.0,
        )
    )

    result = adapter.dispatch_wav(wav)

    assert result.returncode == 0
    assert calls["shell"] is False
    assert calls["timeout"] == 3.0
    assert calls["command"][0] == str(exe)


def test_dispatch_timeout_returns_safe_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe = tmp_path / "DCS-SR-ExternalAudio.exe"
    exe.write_text("stub", encoding="utf-8")
    wav = tmp_path / "input.wav"
    wav.write_bytes(b"RIFF")

    def fake_run(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="srs", timeout=1)

    monkeypatch.setattr(srs_audio.subprocess, "run", fake_run)
    adapter = SrsExternalAudioAdapter(
        SrsAudioConfig(enabled=True, external_audio_exe=str(exe), output_dir=str(tmp_path / "out"))
    )

    result = adapter.dispatch_wav(wav)

    assert result.returncode is None
    assert "timed out" in result.message
