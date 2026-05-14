from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from voice_comms_dcs.radio_voice import RadioVoice, RadioVoiceConfig
from voice_comms_dcs.srs_audio import SrsAudioConfig, SrsExternalAudioAdapter
from voice_comms_dcs.stt_whisper_engine import WhisperCliBackend, WhisperConfig


def test_whisper_cli_passes_timeout(monkeypatch, tmp_path):
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    seen = {}

    def fake_run(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        output_base = Path(args[0][args[0].index("-of") + 1])
        output_base.with_suffix(".txt").write_text("request tanker", encoding="utf-8")
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = WhisperCliBackend(WhisperConfig(model_path=str(model), engine="cli", cli_timeout_seconds=7.5))
    assert backend.transcribe(np.ones(160, dtype=np.float32), 16000) == "request tanker"
    assert seen["timeout"] == 7.5


def test_whisper_cli_timeout_is_sanitized_and_temp_files_removed(monkeypatch, tmp_path):
    model = tmp_path / "private-model.bin"
    model.write_bytes(b"model")
    temp_paths: list[Path] = []

    def fake_write_temp_wav(samples, sample_rate):
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"wav")
        wav.with_suffix(".txt").write_text("partial", encoding="utf-8")
        temp_paths.extend([wav, wav.with_suffix(".txt")])
        return wav

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr("voice_comms_dcs.stt_whisper_engine.write_temp_wav", fake_write_temp_wav)
    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = WhisperCliBackend(WhisperConfig(model_path=str(model), engine="cli", cli_timeout_seconds=2.0))
    with pytest.raises(TimeoutError) as excinfo:
        backend.transcribe(np.ones(160, dtype=np.float32), 16000)
    message = str(excinfo.value)
    assert "timed out after 2 seconds" in message
    assert str(model) not in message
    assert all(not path.exists() for path in temp_paths)


def test_radio_voice_run_piper_passes_timeout(monkeypatch, tmp_path):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    output = tmp_path / "out.wav"
    seen = {}

    def fake_run(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        output.write_bytes(b"wav")
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    voice = RadioVoice(RadioVoiceConfig(piper_model=str(model), piper_timeout_seconds=4.0))
    voice._run_piper("hello", output)
    assert seen["timeout"] == 4.0


def test_radio_voice_timeout_is_sanitized_and_partial_output_removed(monkeypatch, tmp_path):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    output = tmp_path / "out.wav"
    output.write_bytes(b"partial")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    voice = RadioVoice(RadioVoiceConfig(piper_model=str(model), piper_timeout_seconds=3.0))
    with pytest.raises(RuntimeError) as excinfo:
        voice._run_piper("hello", output)
    message = str(excinfo.value)
    assert message == "Piper synthesis timed out after 3 seconds"
    assert str(model) not in message
    assert not output.exists()


def test_srs_dispatch_timeout_returns_nonfatal_result(monkeypatch, tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"wav")
    exe = tmp_path / "srs.exe"
    exe.write_bytes(b"exe")
    seen = {}

    def fake_run(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = SrsExternalAudioAdapter(
        SrsAudioConfig(enabled=True, external_audio_exe=str(exe), output_dir=str(tmp_path / "out"), timeout_seconds=1.5)
    )
    result = adapter.dispatch_wav(source)
    assert seen["timeout"] == 1.5
    assert result.enabled is True
    assert result.returncode is None
    assert result.stderr == ""
    assert result.message == "SRS external audio command timed out."
