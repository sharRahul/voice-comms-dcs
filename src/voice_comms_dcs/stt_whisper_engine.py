from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import time
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from scipy.signal import butter, lfilter

from .language_models import get_whisper_language_code


DEFAULT_SAMPLE_RATE = 16000


@dataclass(frozen=True)
class WhisperConfig:
    """Whisper.cpp local STT configuration.

    Use `tiny.en` or `base.en` for English-only command recognition. Use multilingual
    `tiny` or `base` weights for Chinese, Korean, French, Russian, and Spanish.
    """

    model_path: str = "models/whisper/ggml-base.en.bin"
    sample_rate: int = DEFAULT_SAMPLE_RATE
    language: str = "en"
    max_context_ms: int = 15000
    pre_roll_ms: int = 500
    engine: str = "auto"  # auto, binding, cli
    cli_exe: str = "whisper-cli"
    threads: int = 4
    beam_size: int = 1
    highpass_hz: float = 120.0
    lowpass_hz: float = 7600.0


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    duration_seconds: float
    audio_seconds: float
    engine: str
    language: str


class WhisperBackend(Protocol):
    def transcribe(self, samples: np.ndarray, sample_rate: int) -> str: ...


class RollingAudioBuffer:
    """Thread-light rolling buffer with 500 ms pre-roll support.

    Audio is continuously appended from WebRTC frames. When PTT starts, the active utterance is
    initialised with the last pre-roll samples so the first word is not clipped. When PTT stops,
    the utterance is returned and reset.
    """

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, pre_roll_ms: int = 500) -> None:
        self.sample_rate = sample_rate
        self.pre_roll_samples = int(sample_rate * pre_roll_ms / 1000)
        self._pre_roll: deque[float] = deque(maxlen=self.pre_roll_samples)
        self._active_chunks: list[np.ndarray] = []
        self._recording = False

    @property
    def recording(self) -> bool:
        return self._recording

    def append(self, samples: np.ndarray, source_rate: int) -> None:
        prepared = prepare_audio(samples, source_rate=source_rate, target_rate=self.sample_rate)
        if prepared.size == 0:
            return
        self._pre_roll.extend(float(x) for x in prepared)
        if self._recording:
            self._active_chunks.append(prepared)

    def start_ptt(self) -> None:
        self._recording = True
        pre_roll = np.array(list(self._pre_roll), dtype=np.float32)
        self._active_chunks = [pre_roll] if pre_roll.size else []

    def stop_ptt(self) -> np.ndarray:
        self._recording = False
        if not self._active_chunks:
            return np.zeros(0, dtype=np.float32)
        utterance = np.concatenate(self._active_chunks).astype(np.float32)
        self._active_chunks = []
        return utterance

    def clear(self) -> None:
        self._active_chunks = []
        self._recording = False


class WhisperCppPythonBackend:
    def __init__(self, config: WhisperConfig) -> None:
        try:
            from whisper_cpp_python import Whisper  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional package build
            raise RuntimeError("whisper-cpp-python is not available") from exc

        self.config = config
        self._model = Whisper(model_path=config.model_path)

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> str:
        wav_path = write_temp_wav(samples, sample_rate)
        try:
            result = self._model.transcribe(str(wav_path), language=self.config.language)
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(result, dict):
            return str(result.get("text", "")).strip()
        return str(result).strip()


class WhisperCliBackend:
    def __init__(self, config: WhisperConfig) -> None:
        self.config = config
        exe = shutil.which(config.cli_exe) or config.cli_exe
        self.exe = exe
        if not Path(config.model_path).exists():
            raise FileNotFoundError(f"Whisper model not found: {config.model_path}")

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> str:
        wav_path = write_temp_wav(samples, sample_rate)
        output_base = wav_path.with_suffix("")
        try:
            process = subprocess.run(
                [
                    self.exe,
                    "-m",
                    self.config.model_path,
                    "-f",
                    str(wav_path),
                    "-l",
                    self.config.language,
                    "-t",
                    str(self.config.threads),
                    "-bs",
                    str(self.config.beam_size),
                    "-otxt",
                    "-of",
                    str(output_base),
                    "-nt",
                ],
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
            txt_path = output_base.with_suffix(".txt")
            if txt_path.exists():
                return txt_path.read_text(encoding="utf-8", errors="replace").strip()
            if process.returncode != 0:
                raise RuntimeError(process.stderr.strip() or f"whisper.cpp exited {process.returncode}")
            return process.stdout.strip()
        finally:
            for path in (wav_path, output_base.with_suffix(".txt")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


class WhisperSttEngine:
    """High-fidelity local STT engine for PTT-gated WebRTC audio."""

    def __init__(self, config: WhisperConfig | None = None) -> None:
        self.config = config or WhisperConfig()
        self.backend = self._create_backend()

    def transcribe(self, samples: np.ndarray, source_rate: int) -> TranscriptionResult:
        started = time.perf_counter()
        prepared = prepare_audio(
            samples,
            source_rate=source_rate,
            target_rate=self.config.sample_rate,
            highpass_hz=self.config.highpass_hz,
            lowpass_hz=self.config.lowpass_hz,
        )
        if prepared.size == 0:
            return TranscriptionResult("", 0.0, 0.0, self.config.engine, self.config.language)
        audio_seconds = prepared.size / float(self.config.sample_rate)
        text = self.backend.transcribe(prepared, self.config.sample_rate)
        elapsed = time.perf_counter() - started
        return TranscriptionResult(
            text=clean_transcript(text),
            duration_seconds=elapsed,
            audio_seconds=audio_seconds,
            engine=self.backend.__class__.__name__,
            language=self.config.language,
        )

    def _create_backend(self) -> WhisperBackend:
        if self.config.engine in {"auto", "binding"}:
            try:
                return WhisperCppPythonBackend(self.config)
            except Exception:
                if self.config.engine == "binding":
                    raise
        return WhisperCliBackend(self.config)


def prepare_audio(
    samples: np.ndarray,
    source_rate: int,
    target_rate: int = DEFAULT_SAMPLE_RATE,
    highpass_hz: float = 120.0,
    lowpass_hz: float = 7600.0,
) -> np.ndarray:
    if samples.size == 0:
        return np.zeros(0, dtype=np.float32)
    mono = samples.astype(np.float32)
    if mono.ndim > 1:
        mono = mono.mean(axis=0)
    mono = remove_dc(mono)
    mono = normalise_audio(mono)
    if source_rate != target_rate:
        mono = linear_resample(mono, source_rate, target_rate)
    mono = cockpit_noise_filter(mono, target_rate, highpass_hz, lowpass_hz)
    return normalise_audio(mono).astype(np.float32)


def remove_dc(samples: np.ndarray) -> np.ndarray:
    return (samples - float(np.mean(samples))).astype(np.float32)


def normalise_audio(samples: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak <= 0.00001:
        return samples.astype(np.float32)
    return np.clip(samples / peak * 0.92, -1.0, 1.0).astype(np.float32)


def cockpit_noise_filter(
    samples: np.ndarray,
    sample_rate: int,
    highpass_hz: float,
    lowpass_hz: float,
) -> np.ndarray:
    if samples.size < 32:
        return samples
    nyquist = sample_rate / 2.0
    low = max(20.0, highpass_hz) / nyquist
    high = min(lowpass_hz, nyquist - 100.0) / nyquist
    if not 0 < low < high < 1:
        return samples
    b, a = butter(3, [low, high], btype="bandpass")
    return lfilter(b, a, samples).astype(np.float32)


def linear_resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or samples.size == 0:
        return samples.astype(np.float32)
    duration = samples.size / float(source_rate)
    target_count = max(1, int(duration * target_rate))
    old_x = np.linspace(0.0, duration, num=samples.size, endpoint=False)
    new_x = np.linspace(0.0, duration, num=target_count, endpoint=False)
    return np.interp(new_x, old_x, samples).astype(np.float32)


def clean_transcript(text: str) -> str:
    text = " ".join(text.replace("[BLANK_AUDIO]", "").split())
    return text.strip(" .")


def write_temp_wav(samples: np.ndarray, sample_rate: int) -> Path:
    temp = tempfile.NamedTemporaryFile(prefix="vcdcs-whisper-", suffix=".wav", delete=False)
    temp.close()
    path = Path(temp.name)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return path


def read_wav(path: Path) -> tuple[int, np.ndarray]:
    with wave.open(str(path), "rb") as wav:
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("Only 16-bit PCM WAV is supported for diagnostics.")
    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return sample_rate, data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a local Whisper.cpp transcription test.")
    parser.add_argument("--model", default=WhisperConfig.model_path)
    parser.add_argument("--engine", choices=["auto", "binding", "cli"], default="auto")
    parser.add_argument("--cli-exe", default=WhisperConfig.cli_exe)
    parser.add_argument("--wav", required=True, help="16-bit PCM WAV file to transcribe.")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--lang", default="en", choices=["en", "zh", "ko", "fr", "ru", "es"])
    args = parser.parse_args(argv)

    sample_rate, samples = read_wav(Path(args.wav))
    engine = WhisperSttEngine(
        WhisperConfig(
            model_path=args.model,
            engine=args.engine,
            cli_exe=args.cli_exe,
            threads=args.threads,
            language=get_whisper_language_code(args.lang),
        )
    )
    result = engine.transcribe(samples, sample_rate)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
