from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import butter, lfilter

from .language_models import get_piper_voice


@dataclass(frozen=True)
class RadioVoiceConfig:
    """Configuration for local TTS and radio-style post processing."""

    engine: str = "piper"
    piper_exe: str = "piper"
    piper_model: str = "models/piper/en_US-lessac-low.onnx"
    sample_rate: int = 16000
    language: str = "en"
    bandpass_low_hz: float = 300.0
    bandpass_high_hz: float = 3000.0
    static_level: float = 0.012
    output_gain: float = 0.85


class RadioVoice:
    """Local TTS wrapper with cockpit radio post-processing.

    The default model is `en_US-lessac-low`, which is small and fits the intentional radio-effect
    output. Language-specific Piper voice mappings are provided by `language_models.py`.
    """

    def __init__(self, config: RadioVoiceConfig | None = None) -> None:
        self.config = config or RadioVoiceConfig()

    def synthesise_to_wav(self, text: str, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        if self.config.engine.lower() != "piper":
            raise ValueError(f"Unsupported TTS engine: {self.config.engine}")

        self._run_piper(text=text, output_path=output)
        self.apply_radio_filter(output, output)
        return output

    def synthesise_to_temp_wav(self, text: str) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="voice-comms-dcs-tts-"))
        return self.synthesise_to_wav(text, temp_dir / "nimbus_radio.wav")

    def _run_piper(self, text: str, output_path: Path) -> None:
        exe = shutil.which(self.config.piper_exe) or self.config.piper_exe
        model_path = Path(self.config.piper_model)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Piper model not found: {model_path}. Update RadioVoiceConfig.piper_model "
                "or run python -m voice_comms_dcs.dependency_manager --languages en --all."
            )

        process = subprocess.run(
            [exe, "--model", str(model_path), "--output_file", str(output_path)],
            input=text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(
                "Piper failed: "
                + (process.stderr.strip() or process.stdout.strip() or f"exit {process.returncode}")
            )

    def apply_radio_filter(self, input_path: str | Path, output_path: str | Path) -> Path:
        input_wav = Path(input_path)
        output_wav = Path(output_path)
        sample_rate, samples = read_wav_mono(input_wav)
        filtered = radio_filter(
            samples=samples,
            sample_rate=sample_rate,
            low_hz=self.config.bandpass_low_hz,
            high_hz=self.config.bandpass_high_hz,
            static_level=self.config.static_level,
            output_gain=self.config.output_gain,
        )
        write_wav_mono(output_wav, sample_rate, filtered)
        return output_wav


def config_for_language(
    language: str,
    piper_exe: str = "piper",
    static_level: float = 0.012,
) -> RadioVoiceConfig:
    voice = get_piper_voice(language)
    return RadioVoiceConfig(
        piper_exe=piper_exe,
        piper_model=voice.model_path,
        language=language,
        static_level=static_level,
    )


def radio_filter(
    samples: np.ndarray,
    sample_rate: int,
    low_hz: float = 300.0,
    high_hz: float = 3000.0,
    static_level: float = 0.012,
    output_gain: float = 0.85,
) -> np.ndarray:
    """Apply a lightweight cockpit radio effect.

    Processing chain:
    1. Bandpass 300 Hz to 3 kHz.
    2. Gentle tanh compression.
    3. Slight white noise overlay.
    4. Output normalisation.
    """
    if samples.size == 0:
        return samples

    nyquist = 0.5 * sample_rate
    low = max(10.0, low_hz) / nyquist
    high = min(high_hz, nyquist - 100.0) / nyquist
    if low >= high:
        low, high = 300.0 / nyquist, min(3000.0, nyquist - 100.0) / nyquist

    b, a = butter(4, [low, high], btype="band")
    filtered = lfilter(b, a, samples.astype(np.float32))
    compressed = np.tanh(filtered * 1.8)
    noise = np.random.default_rng().normal(0.0, static_level, size=compressed.shape)
    mixed = compressed + noise.astype(np.float32)
    peak = float(np.max(np.abs(mixed)))
    if peak > 0:
        mixed = mixed / peak * output_gain
    return mixed.astype(np.float32)


def read_wav_mono(path: Path) -> tuple[int, np.ndarray]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())

    if sample_width != 2:
        raise ValueError("Only 16-bit PCM WAV files are currently supported.")

    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return sample_rate, data


def write_wav_mono(path: Path, sample_rate: int, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a local Nimbus radio-voice WAV file.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", default="build_output/nimbus_radio.wav")
    parser.add_argument("--model", default=RadioVoiceConfig.piper_model)
    parser.add_argument("--piper-exe", default=RadioVoiceConfig.piper_exe)
    parser.add_argument("--lang", default="en", choices=["en", "zh", "ko", "fr", "ru", "es"])
    parser.add_argument("--use-language-model", action="store_true")
    args = parser.parse_args(argv)

    config = config_for_language(args.lang, args.piper_exe) if args.use_language_model else RadioVoiceConfig(
        piper_exe=args.piper_exe,
        piper_model=args.model,
        language=args.lang,
    )
    voice = RadioVoice(config)
    output = voice.synthesise_to_wav(args.text, args.output)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
