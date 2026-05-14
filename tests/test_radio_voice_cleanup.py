from __future__ import annotations

from pathlib import Path

from voice_comms_dcs.radio_voice import RadioVoice


def test_synthesise_to_temp_wav_cleanup_removes_temp_dir(monkeypatch):
    voice = RadioVoice()

    def fake_synth(text: str, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"wav")
        return output

    monkeypatch.setattr(voice, "synthesise_to_wav", fake_synth)
    wav = voice.synthesise_to_temp_wav("hello")
    root = wav.parent
    assert root.exists()
    voice.cleanup_temp_wav(wav)
    assert not root.exists()


def test_cleanup_temp_wav_does_not_delete_user_directory(tmp_path):
    voice = RadioVoice()
    user_dir = tmp_path / "user-output"
    user_dir.mkdir()
    wav = user_dir / "out.wav"
    wav.write_bytes(b"wav")
    voice.cleanup_temp_wav(wav)
    assert user_dir.exists()
    assert wav.exists()
