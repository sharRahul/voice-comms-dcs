from __future__ import annotations

import argparse
import asyncio
import json
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import numpy as np
from aiohttp import WSMsgType, web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack, MediaStreamError, MediaStreamTrack

from .aircraft_profiles import AircraftProfile, load_aircraft_profile
from .api_routes import DashboardEventHub, setup_dashboard_routes
from .config import load_config
from .context_manager import ContextManager
from .input_manager import (
    InputManager,
    InputManagerConfig,
    JoystickButtonBinding,
    KeyboardBinding,
    PttEvent,
    PttEventType,
)
from .language_models import WHISPER_MODELS, get_piper_voice, get_whisper_language_code, get_whisper_model_key
from .nimbus_intelligence import NimbusIntelligence
from .radio_voice import RadioVoice, RadioVoiceConfig
from .stt_whisper_engine import RollingAudioBuffer, WhisperConfig, WhisperSttEngine
from .telemetry_listener import TelemetryListener

AUDIO_SAMPLE_RATE = 48000
AUDIO_FRAME_SAMPLES = 960
WHISPER_SAMPLE_RATE = 16000


class EnergyVad:
    def __init__(self, rms_threshold: float = 0.012, hangover_frames: int = 8) -> None:
        self.rms_threshold = rms_threshold
        self.hangover_frames = hangover_frames
        self._hangover = 0

    def is_speech(self, samples: np.ndarray) -> bool:
        if samples.size == 0:
            return False
        rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float32)))))
        if rms >= self.rms_threshold:
            self._hangover = self.hangover_frames
            return True
        if self._hangover > 0:
            self._hangover -= 1
            return True
        return False


class InboundAudioSink:
    def __init__(self, rolling_buffer: RollingAudioBuffer, vad: EnergyVad | None = None) -> None:
        self.rolling_buffer = rolling_buffer
        self.vad = vad or EnergyVad()
        self.frames_received = 0
        self.speech_frames = 0

    async def consume(self, track: MediaStreamTrack) -> None:
        while True:
            try:
                frame = await track.recv()
            except MediaStreamError:
                break
            if not isinstance(frame, av.AudioFrame):
                continue
            self.frames_received += 1
            pcm = audio_frame_to_float_mono(frame)
            if self.vad.is_speech(pcm) or self.rolling_buffer.recording:
                self.speech_frames += 1
            self.rolling_buffer.append(pcm, source_rate=frame.sample_rate or AUDIO_SAMPLE_RATE)


class NimbusAudioTrack(AudioStreamTrack):
    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=500)
        self._timestamp = 0

    async def recv(self) -> av.AudioFrame:
        await asyncio.sleep(AUDIO_FRAME_SAMPLES / AUDIO_SAMPLE_RATE)
        try:
            samples = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            samples = np.zeros(AUDIO_FRAME_SAMPLES, dtype=np.float32)

        if samples.size < AUDIO_FRAME_SAMPLES:
            samples = np.pad(samples, (0, AUDIO_FRAME_SAMPLES - samples.size))
        elif samples.size > AUDIO_FRAME_SAMPLES:
            samples = samples[:AUDIO_FRAME_SAMPLES]

        pcm = np.clip(samples, -1.0, 1.0)
        pcm_i16 = (pcm * 32767.0).astype(np.int16).reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(pcm_i16, format="s16", layout="mono")
        frame.sample_rate = AUDIO_SAMPLE_RATE
        frame.pts = self._timestamp
        frame.time_base = Fraction(1, AUDIO_SAMPLE_RATE)
        self._timestamp += AUDIO_FRAME_SAMPLES
        return frame

    async def enqueue_wav(self, wav_path: str | Path) -> None:
        path = Path(wav_path)
        with av.open(str(path)) as container:
            stream = next(s for s in container.streams if s.type == "audio")
            for frame in container.decode(stream):
                samples = audio_frame_to_float_mono(frame)
                if frame.sample_rate != AUDIO_SAMPLE_RATE:
                    samples = linear_resample(samples, frame.sample_rate, AUDIO_SAMPLE_RATE)
                for chunk in chunk_audio(samples, AUDIO_FRAME_SAMPLES):
                    if self._queue.full():
                        _ = self._queue.get_nowait()
                    await self._queue.put(chunk)


class WebRtcBridge:
    """Local WebRTC, multilingual STT/TTS, and Nimbus bridge."""

    def __init__(
        self,
        config_path: str,
        host: str = "127.0.0.1",
        port: int = 8765,
        telemetry_host: str = "127.0.0.1",
        telemetry_port: int = 10309,
        aircraft_profile_path: str | None = "config/aircraft_profiles/default.json",
        whisper_model_path: str | None = None,
        whisper_engine: str = "auto",
        whisper_cli_exe: str = "whisper-cli",
        ptt_hotkey: str = "right_ctrl",
        joystick_index: int = 0,
        joystick_button: int = 1,
        enable_input_manager: bool = True,
        language: str | None = None,
    ) -> None:
        self.config_path = config_path
        self.host = host
        self.port = port
        self.config = load_config(config_path)
        self.current_language = language or self.config.language.selected
        self.aircraft_profile: AircraftProfile = load_aircraft_profile(aircraft_profile_path)
        self.context_manager = ContextManager(aircraft_profile=self.aircraft_profile.prompt_identity())
        self.nimbus = NimbusIntelligence(self.config, context_manager=self.context_manager)
        self.nimbus.set_language(self.current_language)
        self.radio_voice = self._create_radio_voice(self.current_language)
        self.telemetry = TelemetryListener(
            host=telemetry_host,
            port=telemetry_port,
            on_telemetry=self.context_manager.update_telemetry,
        )
        self.whisper_engine_name = whisper_engine
        self.whisper_cli_exe = whisper_cli_exe
        self.manual_whisper_model_path = whisper_model_path
        self.whisper_model_path = self._resolve_whisper_model_path(self.current_language)
        self.whisper = self._create_whisper(self.current_language, self.whisper_model_path)
        self.audio_buffer = RollingAudioBuffer(sample_rate=WHISPER_SAMPLE_RATE, pre_roll_ms=500)
        self.dashboard_events = DashboardEventHub()
        self.peer_connections: set[RTCPeerConnection] = set()
        self.audio_tracks: set[NimbusAudioTrack] = set()
        self.enable_input_manager = enable_input_manager
        self.input_manager = InputManager(
            InputManagerConfig(
                joystick_enabled=enable_input_manager,
                keyboard_enabled=enable_input_manager,
                joystick=JoystickButtonBinding(joystick_index, joystick_button),
                keyboard=KeyboardBinding(ptt_hotkey),
            )
        )
        self._ptt_source = "idle"
        self._last_transcript = ""
        self._last_stt_latency = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None

        self.app = web.Application()
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/ws", self.websocket)
        setup_dashboard_routes(
            self.app,
            context_manager=self.context_manager,
            telemetry_listener=self.telemetry,
            event_hub=self.dashboard_events,
            ptt_state_provider=self.ptt_state,
            language_provider=lambda: self.current_language,
            language_setter=self.set_language,
        )
        self.app.on_startup.append(self._on_startup)
        self.app.on_cleanup.append(self._on_cleanup)

    def _resolve_whisper_model_path(self, language: str) -> str:
        if self.manual_whisper_model_path:
            return self.manual_whisper_model_path
        key = get_whisper_model_key(language, "base")
        path = WHISPER_MODELS[key].model_path
        return path if Path(path).exists() else self.config.stt.model_path

    def _create_whisper(self, language: str, model_path: str) -> WhisperSttEngine:
        return WhisperSttEngine(
            WhisperConfig(
                model_path=model_path,
                engine=self.whisper_engine_name,
                cli_exe=self.whisper_cli_exe,
                language=get_whisper_language_code(language),
            )
        )

    def _create_radio_voice(self, language: str) -> RadioVoice:
        voice = get_piper_voice(language)
        return RadioVoice(
            RadioVoiceConfig(
                piper_exe=self.config.tts.piper_exe,
                piper_model=voice.model_path,
                language=language,
                static_level=self.config.tts.static_level,
                bandpass_low_hz=self.config.tts.bandpass_low_hz,
                bandpass_high_hz=self.config.tts.bandpass_high_hz,
            )
        )

    def set_language(self, language: str) -> None:
        self.current_language = language
        self.nimbus.set_language(language)
        self.radio_voice = self._create_radio_voice(language)
        self.whisper_model_path = self._resolve_whisper_model_path(language)
        self.whisper = self._create_whisper(language, self.whisper_model_path)

    async def _on_startup(self, _app: web.Application) -> None:
        self._loop = asyncio.get_running_loop()
        self.telemetry.start()
        if self.enable_input_manager:
            self.input_manager.subscribe(self._handle_ptt_event_threadsafe)
            self.input_manager.start()
        await self.dashboard_events.broadcast({"type": "system", "message": "Nimbus bridge started"})

    async def _on_cleanup(self, _app: web.Application) -> None:
        if self.enable_input_manager:
            self.input_manager.stop()
        self.telemetry.stop()
        self.nimbus.close()
        await asyncio.gather(*(pc.close() for pc in self.peer_connections), return_exceptions=True)
        self.peer_connections.clear()

    async def index(self, _request: web.Request) -> web.Response:
        raise web.HTTPFound("/dashboard")

    async def health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "language": self.current_language, "whisper_model": self.whisper_model_path, "peers": len(self.peer_connections), "aircraft_profile": self.aircraft_profile.id, "telemetry_age_seconds": self.telemetry.latest().age_seconds, "context": self.context_manager.get_context().prompt_prefix, "ptt": self.ptt_state()})

    def ptt_state(self) -> dict[str, Any]:
        return {"active": self.audio_buffer.recording, "source": self._ptt_source, "last_transcript": self._last_transcript, "last_stt_latency_seconds": self._last_stt_latency, "language": self.current_language, "whisper_model": self.whisper_model_path}

    def _handle_ptt_event_threadsafe(self, event: PttEvent) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._handle_ptt_event(event)))

    async def _handle_ptt_event(self, event: PttEvent) -> None:
        self._ptt_source = f"{event.source}:{event.detail}"
        if event.type is PttEventType.START_PTT:
            self.audio_buffer.start_ptt()
            await self.dashboard_events.broadcast({"type": "ptt", "state": self.ptt_state()})
            return

        utterance = self.audio_buffer.stop_ptt()
        await self.dashboard_events.broadcast({"type": "ptt", "state": self.ptt_state()})
        if utterance.size < int(0.18 * WHISPER_SAMPLE_RATE):
            return
        await self._transcribe_and_process(utterance)

    async def _transcribe_and_process(self, utterance: np.ndarray) -> None:
        started = time.perf_counter()
        try:
            result = await asyncio.to_thread(self.whisper.transcribe, utterance, WHISPER_SAMPLE_RATE)
        except Exception as exc:
            await self.dashboard_events.broadcast({"type": "error", "message": f"Whisper failed: {exc}"})
            return
        self._last_stt_latency = result.duration_seconds
        transcript = result.text.strip()
        self._last_transcript = transcript
        await self.dashboard_events.broadcast({"type": "transcript", "speaker": "pilot", "text": transcript, "language": result.language, "stt_latency_seconds": result.duration_seconds, "audio_seconds": result.audio_seconds, "total_elapsed_seconds": time.perf_counter() - started})
        if transcript:
            await self._process_transcript(transcript, None)

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        pc = RTCPeerConnection()
        outbound_audio = NimbusAudioTrack()
        inbound_audio = InboundAudioSink(self.audio_buffer)
        pc.addTrack(outbound_audio)
        self.peer_connections.add(pc)
        self.audio_tracks.add(outbound_audio)

        @pc.on("track")
        def on_track(track: MediaStreamTrack) -> None:
            if track.kind == "audio":
                asyncio.create_task(inbound_audio.consume(track))

        @pc.on("datachannel")
        def on_datachannel(channel: Any) -> None:
            @channel.on("message")
            def on_message(message: str) -> None:
                asyncio.create_task(self._process_transcript(str(message), lambda text: channel.send(text)))

        try:
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    continue
                payload = json.loads(message.data)
                message_type = payload.get("type")

                if message_type == "offer":
                    offer = RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
                    await pc.setRemoteDescription(offer)
                    answer = await pc.createAnswer()
                    await pc.setLocalDescription(answer)
                    await ws.send_json({"type": pc.localDescription.type, "sdp": pc.localDescription.sdp})
                elif message_type == "transcript":
                    await self._process_transcript(str(payload.get("text", "")), lambda text: asyncio.create_task(ws.send_json({"type": "nimbus", "text": text})))
                elif message_type == "ptt_start":
                    await self._handle_ptt_event(PttEvent(PttEventType.START_PTT, "dashboard", time.monotonic()))
                elif message_type == "ptt_stop":
                    await self._handle_ptt_event(PttEvent(PttEventType.STOP_PTT, "dashboard", time.monotonic()))
                elif message_type == "language":
                    self.set_language(str(payload.get("language", "en")))
                    await ws.send_json({"type": "language", "language": self.current_language})
                elif message_type == "ping":
                    await ws.send_json({"type": "pong", "time": time.time()})
        finally:
            self.peer_connections.discard(pc)
            self.audio_tracks.discard(outbound_audio)
            await pc.close()
        return ws

    async def _process_transcript(self, text: str, reply: Any | None) -> None:
        text = text.strip()
        if not text:
            return
        started = time.perf_counter()
        decision, _dispatch = self.nimbus.handle_pilot_text(text)
        response = decision.response_text
        await self.dashboard_events.broadcast({"type": "conversation", "pilot": text, "nimbus": response, "language": self.current_language, "intent": decision.intent.value, "command_id": decision.command_id, "elapsed_seconds": time.perf_counter() - started})
        if reply is not None:
            maybe_reply = reply(response)
            if asyncio.iscoroutine(maybe_reply):
                await maybe_reply
        await self._speak_response(response)

    async def _speak_response(self, response: str) -> None:
        try:
            wav = await asyncio.to_thread(self.radio_voice.synthesise_to_temp_wav, response)
            await asyncio.gather(*(track.enqueue_wav(wav) for track in list(self.audio_tracks)), return_exceptions=True)
        except Exception as exc:
            await self.dashboard_events.broadcast({"type": "error", "message": f"TTS failed: {exc}"})

    def run(self) -> None:
        web.run_app(self.app, host=self.host, port=self.port)


def audio_frame_to_float_mono(frame: av.AudioFrame) -> np.ndarray:
    array = frame.to_ndarray()
    if array.size == 0:
        return np.zeros(0, dtype=np.float32)
    if array.ndim == 2:
        array = array.mean(axis=0)
    array = array.astype(np.float32)
    if np.max(np.abs(array)) > 1.5:
        array = array / 32768.0
    return array.astype(np.float32)


def linear_resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or samples.size == 0:
        return samples.astype(np.float32)
    duration = samples.size / float(source_rate)
    target_count = max(1, int(duration * target_rate))
    old_x = np.linspace(0.0, duration, num=samples.size, endpoint=False)
    new_x = np.linspace(0.0, duration, num=target_count, endpoint=False)
    return np.interp(new_x, old_x, samples).astype(np.float32)


def chunk_audio(samples: np.ndarray, chunk_size: int) -> list[np.ndarray]:
    return [samples[i : i + chunk_size] for i in range(0, samples.size, chunk_size)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local Voice-Comms-DCS WebRTC bridge.")
    parser.add_argument("--config", default="config/commands.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--telemetry-host", default="127.0.0.1")
    parser.add_argument("--telemetry-port", type=int, default=10309)
    parser.add_argument("--aircraft-profile", default="config/aircraft_profiles/default.json")
    parser.add_argument("--whisper-model")
    parser.add_argument("--whisper-engine", choices=["auto", "binding", "cli"], default="auto")
    parser.add_argument("--whisper-cli-exe", default="whisper-cli")
    parser.add_argument("--ptt-hotkey", default="right_ctrl")
    parser.add_argument("--joystick-index", type=int, default=0)
    parser.add_argument("--joystick-button", type=int, default=1)
    parser.add_argument("--language", choices=["en", "zh", "ko", "fr", "ru", "es"])
    parser.add_argument("--disable-input-manager", action="store_true")
    args = parser.parse_args(argv)

    bridge = WebRtcBridge(
        config_path=args.config,
        host=args.host,
        port=args.port,
        telemetry_host=args.telemetry_host,
        telemetry_port=args.telemetry_port,
        aircraft_profile_path=args.aircraft_profile,
        whisper_model_path=args.whisper_model,
        whisper_engine=args.whisper_engine,
        whisper_cli_exe=args.whisper_cli_exe,
        ptt_hotkey=args.ptt_hotkey,
        joystick_index=args.joystick_index,
        joystick_button=args.joystick_button,
        enable_input_manager=not args.disable_input_manager,
        language=args.language,
    )
    bridge.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
