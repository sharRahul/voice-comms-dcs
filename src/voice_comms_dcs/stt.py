from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Callable

import sounddevice as sd
from vosk import KaldiRecognizer, Model

from .config import SttConfig

TranscriptCallback = Callable[[str], None]
StatusCallback = Callable[[str], None]


class SttRuntimeError(RuntimeError):
    """Raised when the configured speech-to-text backend cannot be started."""


class VoskListener:
    """Small offline STT listener built around Vosk and sounddevice."""

    def __init__(
        self,
        config: SttConfig,
        on_transcript: TranscriptCallback,
        on_status: StatusCallback | None = None,
    ) -> None:
        self.config = config
        self.on_transcript = on_transcript
        self.on_status = on_status or (lambda _message: None)
        self._audio_queue: queue.Queue[bytes] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream: sd.RawInputStream | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return

        model_path = Path(self.config.model_path)
        if not model_path.exists():
            raise SttRuntimeError(
                f"Vosk model not found at {model_path}. Download a Vosk model and update commands.json."
            )

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, args=(model_path,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _audio_callback(self, indata: bytes, _frames: int, _time: object, status: object) -> None:
        if status:
            self.on_status(f"Audio status: {status}")
        self._audio_queue.put(bytes(indata))

    def _run(self, model_path: Path) -> None:
        self.on_status("Loading Vosk model...")
        model = Model(str(model_path))
        recognizer = KaldiRecognizer(model, self.config.sample_rate)

        self._stream = sd.RawInputStream(
            samplerate=self.config.sample_rate,
            blocksize=8000,
            device=self.config.device,
            dtype="int16",
            channels=1,
            callback=self._audio_callback,
        )

        with self._stream:
            self.on_status("Listening")
            while not self._stop_event.is_set():
                try:
                    data = self._audio_queue.get(timeout=0.25)
                except queue.Empty:
                    continue

                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = str(result.get("text", "")).strip()
                    if text:
                        self.on_transcript(text)

        self.on_status("Stopped")
