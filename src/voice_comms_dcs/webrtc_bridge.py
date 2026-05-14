from __future__ import annotations

import argparse
import asyncio
import json
import logging
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
from .config import load_config, resolve_bridge_runtime_config
from .context_manager import ContextManager
from .dashboard_security import (
    DashboardSecurity,
    DashboardSecurityConfig,
    DashboardValidationError,
    safe_error_event,
    validate_ws_message,
)
from .dashboard_settings import DashboardSettings
from .input_manager import (
    InputManager,
    InputManagerConfig,
    JoystickButtonBinding,
    KeyboardBinding,
    PttEvent,
    PttEventType,
)
from .input_profiles import JoystickPreset, resolve_joystick_preset
from .language_models import WHISPER_MODELS, get_piper_voice, get_whisper_language_code, get_whisper_model_key
from .nimbus_intelligence import NimbusIntelligence
from .radio_voice import RadioVoice, RadioVoiceConfig
from .rwr_adapters import RwrAdapterRegistry
from .srs_audio import SrsExternalAudioAdapter
from .stt_whisper_engine import RollingAudioBuffer, WhisperConfig, WhisperSttEngine
from .telemetry_listener import TelemetryListener

AUDIO_SAMPLE_RATE = 48000
AUDIO_FRAME_SAMPLES = 960
WHISPER_SAMPLE_RATE = 16000
logger = logging.getLogger(__name__)


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
                if not isinstance(frame, av.AudioFrame):
                    continue
                samples = audio_frame_to_float_mono(frame)
                if frame.sample_rate != AUDIO_SAMPLE_RATE:
                    samples = linear_resample(samples, frame.sample_rate, AUDIO_SAMPLE_RATE)
                for chunk in chunk_audio(samples, AUDIO_FRAME_SAMPLES):
                    if self._queue.full():
                        _ = self._queue.get_nowait()
                    await self._queue.put(chunk)


class WebRtcBridge:
    """Local WebRTC, multilingual STT/TTS, dashboard settings, RWR, SRS, and Nimbus bridge."""

    def __init__(
        self,
        config_path: str,
        host: str | None = None,
        port: int | None = None,
        telemetry_host: str | None = None,
        telemetry_port: int | None = None,
        aircraft_profile_path: str | None = "config/aircraft_profiles/default.json",
        whisper_model_path: str | None = None,
        whisper_engine: str | None = None,
        whisper_cli_exe: str | None = None,
        ptt_hotkey: str | None = None,
        joystick_index: int | None = None,
        joystick_button: int | None = None,
        joystick_profile: str | None = None,
        enable_input_manager: bool | None = None,
        language: str | None = None,
        personality: str = "professional",
        skin: str = "default",
        rwr_profile: str | None = None,
        rwr_registry_path: str = "config/rwr/adapters.json",
        srs_config_path: str = "config/srs/srs_audio.json",
        dashboard_token: str | None = None,
        dashboard_auth_enabled: bool = True,
        allow_lan: bool = False,
        allowed_origins: tuple[str, ...] = (),
    ) -> None:
        self.config_path = config_path
        self.config = load_config(config_path)
        self.runtime_config = resolve_bridge_runtime_config(
            self.config,
            host=host,
            port=port,
            telemetry_host=telemetry_host,
            telemetry_port=telemetry_port,
            ptt_hotkey=ptt_hotkey,
            joystick_index=joystick_index,
            joystick_button=joystick_button,
            enable_input_manager=enable_input_manager,
        )
        self.host = self.runtime_config.host
        self.port = self.runtime_config.port
        self.security = DashboardSecurity(
            DashboardSecurityConfig(
                host=self.host,
                port=self.port,
                token=dashboard_token,
                auth_enabled=dashboard_auth_enabled,
                allow_lan=allow_lan,
                allowed_origins=allowed_origins,
            )
        )
        self._llm_timeout_seconds = max(float(self.config.llm.timeout_seconds) + 1.0, 1.0)
        self.current_language = language or self.config.language.selected
        self.settings = DashboardSettings(personality=personality, skin=skin)
        self.aircraft_profile: AircraftProfile = load_aircraft_profile(aircraft_profile_path)
        self.context_manager = ContextManager(aircraft_profile=self.aircraft_profile.prompt_identity())
        self.rwr_profile = rwr_profile
        self.rwr_registry = RwrAdapterRegistry.from_json(rwr_registry_path)
        self.srs_adapter = (
            SrsExternalAudioAdapter.from_json(srs_config_path)
            if Path(srs_config_path).exists()
            else SrsExternalAudioAdapter()
        )
        self.nimbus = NimbusIntelligence(
            self.config,
            context_manager=self.context_manager,
            personality=self.settings.snapshot().personality,
        )
        self.nimbus.set_language(self.current_language)
        self.radio_voice = self._create_radio_voice(self.current_language)
        self.telemetry = TelemetryListener(
            host=self.runtime_config.telemetry_host,
            port=self.runtime_config.telemetry_port,
            on_telemetry=self._handle_telemetry,
        )
        self.whisper_engine_name = whisper_engine if whisper_engine is not None else self.config.stt.whisper_engine
        self.whisper_cli_exe = whisper_cli_exe if whisper_cli_exe is not None else self.config.stt.cli_exe
        self.manual_whisper_model_path = whisper_model_path
        self.whisper_model_path = self._resolve_whisper_model_path(self.current_language)
        self.whisper = self._create_whisper(self.current_language, self.whisper_model_path)
        self.audio_buffer = RollingAudioBuffer(
            sample_rate=WHISPER_SAMPLE_RATE,
            pre_roll_ms=self.runtime_config.pre_roll_ms,
            max_context_ms=self.runtime_config.max_context_ms,
        )
        self.dashboard_events = DashboardEventHub()
        self.peer_connections: set[RTCPeerConnection] = set()
        self.audio_tracks: set[NimbusAudioTrack] = set()
        self.active_joystick_preset: JoystickPreset | None = resolve_joystick_preset(joystick_profile)
        runtime_joystick_index = self.runtime_config.joystick_index
        runtime_joystick_button = self.runtime_config.joystick_button
        runtime_ptt_hotkey = self.runtime_config.ptt_hotkey
        if self.active_joystick_preset:
            runtime_joystick_index = self.active_joystick_preset.joystick_index
            runtime_joystick_button = self.active_joystick_preset.button_index
            runtime_ptt_hotkey = self.active_joystick_preset.hotkey
        self.input_manager = InputManager(
            InputManagerConfig(
                joystick_enabled=self.runtime_config.joystick_enabled,
                keyboard_enabled=self.runtime_config.keyboard_enabled,
                joystick=JoystickButtonBinding(runtime_joystick_index, runtime_joystick_button),
                keyboard=KeyboardBinding(runtime_ptt_hotkey),
                poll_hz=self.runtime_config.poll_hz,
            )
        )
        self.enable_input_manager = self.runtime_config.keyboard_enabled or self.runtime_config.joystick_enabled
        self._ptt_source = "idle"
        self._last_transcript = ""
        self._last_stt_latency = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._llm_semaphore = asyncio.Semaphore(1)

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
            settings_provider=self.settings.snapshot,
            personality_setter=self.set_personality,
            skin_setter=self.set_skin,
            joystick_preset_setter=self.set_joystick_preset,
            security=self.security,
        )
        self.app.on_startup.append(self._on_startup)
        self.app.on_cleanup.append(self._on_cleanup)

    def _handle_telemetry(self, telemetry: dict[str, Any]) -> None:
        normalised = self.rwr_registry.normalise_telemetry(telemetry, self.rwr_profile)
        self.context_manager.update_telemetry(normalised)

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
                threads=self.config.stt.threads,
                beam_size=self.config.stt.beam_size,
                highpass_hz=self.config.stt.highpass_hz,
                lowpass_hz=self.config.stt.lowpass_hz,
                pre_roll_ms=self.config.stt.pre_roll_ms,
                max_context_ms=self.config.stt.max_context_ms,
                cli_timeout_seconds=self.config.stt.cli_timeout_seconds,
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
                piper_timeout_seconds=self.config.tts.piper_timeout_seconds,
            )
        )

    def set_language(self, language: str) -> None:
        self.current_language = language
        self.nimbus.set_language(language)
        self.radio_voice = self._create_radio_voice(language)
        self.whisper_model_path = self._resolve_whisper_model_path(language)
        self.whisper = self._create_whisper(language, self.whisper_model_path)

    def set_personality(self, personality: str) -> None:
        snapshot = self.settings.set_personality(personality)
        self.nimbus.set_personality(snapshot.personality)

    def set_skin(self, skin: str) -> None:
        self.settings.set_skin(skin)

    def set_joystick_preset(self, profile_id: str) -> JoystickPreset:
        preset = resolve_joystick_preset(profile_id)
        if preset is None:
            raise ValueError(f"Unknown joystick preset: {profile_id}")
        was_running = self.enable_input_manager
        if was_running:
            self.input_manager.stop()
        self.active_joystick_preset = preset
        self.input_manager = InputManager(preset.to_input_config(joystick_enabled=was_running, keyboard_enabled=was_running))
        if was_running:
            self.input_manager.subscribe(self._handle_ptt_event_threadsafe)
            self.input_manager.start()
        return preset

    async def _on_startup(self, _app: web.Application) -> None:
        self._loop = asyncio.get_running_loop()
        logger.info("Dashboard: %s", self.security.dashboard_url())
        print(f"Dashboard: {self.security.dashboard_url()}")
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
        raise web.HTTPFound(self.security.dashboard_url())

    async def health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    def ptt_state(self) -> dict[str, Any]:
        return {
            "active": self.audio_buffer.recording,
            "active_seconds": self.audio_buffer.active_seconds,
            "max_context_ms": self.audio_buffer.max_context_samples,
            "source": self._ptt_source,
            "last_transcript": self._last_transcript,
            "last_stt_latency_seconds": self._last_stt_latency,
            "language": self.current_language,
            "whisper_model": self.whisper_model_path,
            "joystick_preset": self.active_joystick_preset.id if self.active_joystick_preset else None,
        }

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
        except Exception:
            logger.exception("Whisper transcription failed")
            await self.dashboard_events.broadcast(
                safe_error_event("STT_FAILED", "Speech recognition failed. Check local Whisper configuration.")
            )
            return
        self._last_stt_latency = result.duration_seconds
        transcript = result.text.strip()
        self._last_transcript = transcript
        await self.dashboard_events.broadcast(
            {
                "type": "transcript",
                "speaker": "pilot",
                "text": transcript,
                "language": result.language,
                "stt_latency_seconds": result.duration_seconds,
                "audio_seconds": result.audio_seconds,
                "total_elapsed_seconds": time.perf_counter() - started,
            }
        )
        if transcript:
            await self._process_transcript(transcript, None)

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        self.security.require_request(request, check_origin=True)
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        pc = RTCPeerConnection()
        outbound_audio = NimbusAudioTrack()
        inbound_audio = InboundAudioSink(
            self.audio_buffer,
            vad=EnergyVad(
                rms_threshold=self.runtime_config.vad_rms_threshold,
                hangover_frames=self.runtime_config.vad_hangover_frames,
            ),
        )
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
                try:
                    payload = validate_ws_message(json.dumps({"type": "transcript", "text": str(message)}))
                except DashboardValidationError:
                    return
                asyncio.create_task(self._process_transcript(payload["text"], lambda text: channel.send(text)))

        try:
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    continue
                try:
                    payload = validate_ws_message(message.data)
                except DashboardValidationError as exc:
                    await ws.send_json(safe_error_event(exc.code, exc.safe_message))
                    continue
                message_type = payload["type"]

                if message_type == "offer":
                    offer = RTCSessionDescription(sdp=payload["sdp"], type="offer")
                    await pc.setRemoteDescription(offer)
                    answer = await pc.createAnswer()
                    await pc.setLocalDescription(answer)
                    await ws.send_json({"type": pc.localDescription.type, "sdp": pc.localDescription.sdp})
                elif message_type == "transcript":
                    await self._process_transcript(payload["text"], lambda text: asyncio.create_task(ws.send_json({"type": "nimbus", "text": text})))
                elif message_type == "ptt_start":
                    await self._handle_ptt_event(PttEvent(PttEventType.START_PTT, "dashboard", time.monotonic()))
                elif message_type == "ptt_stop":
                    await self._handle_ptt_event(PttEvent(PttEventType.STOP_PTT, "dashboard", time.monotonic()))
                elif message_type == "language":
                    self.set_language(payload["language"])
                    await ws.send_json({"type": "language", "language": self.current_language})
                elif message_type == "settings":
                    if "personality" in payload:
                        self.set_personality(str(payload["personality"]))
                    if "skin" in payload:
                        self.set_skin(str(payload["skin"]))
                    await ws.send_json({"type": "settings", **self.settings.snapshot().__dict__})
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
        try:
            async with self._llm_semaphore:
                decision, _dispatch = await asyncio.wait_for(
                    asyncio.to_thread(self.nimbus.handle_pilot_text, text),
                    timeout=self._llm_timeout_seconds,
                )
        except TimeoutError:
            logger.exception("Nimbus transcript handling timed out")
            await self.dashboard_events.broadcast(
                safe_error_event("NIMBUS_TIMEOUT", "Nimbus processing timed out. Check local model configuration.")
            )
            return
        except Exception:
            logger.exception("Nimbus transcript handling failed")
            await self.dashboard_events.broadcast(
                safe_error_event("NIMBUS_FAILED", "Nimbus processing failed. Check local model configuration.")
            )
            return
        response = decision.response_text
        await self.dashboard_events.broadcast(
            {
                "type": "conversation",
                "pilot": text,
                "nimbus": response,
                "language": self.current_language,
                "settings": self.settings.snapshot().__dict__,
                "intent": decision.intent.value,
                "command_id": decision.command_id,
                "elapsed_seconds": time.perf_counter() - started,
            }
        )
        if reply is not None:
            maybe_reply = reply(response)
            if asyncio.iscoroutine(maybe_reply):
                await maybe_reply
        await self._speak_response(response)

    async def _speak_response(self, response: str) -> None:
        wav: Path | None = None
        try:
            wav = await asyncio.to_thread(self.radio_voice.synthesise_to_temp_wav, response)
            srs_result = await asyncio.to_thread(self.srs_adapter.dispatch_wav, wav, "nimbus")
            if srs_result.enabled:
                audio_file_name = Path(srs_result.audio_file).name
                srs_message = srs_result.message
                if not srs_message:
                    if srs_result.returncode == 0:
                        srs_message = "SRS external audio command executed."
                    elif srs_result.returncode is None:
                        srs_message = "SRS external audio is unavailable. Check local SRS configuration."
                    else:
                        srs_message = "SRS external audio command failed."
                await self.dashboard_events.broadcast(
                    {
                        "type": "srs_audio",
                        "audio_file": audio_file_name,
                        "returncode": srs_result.returncode,
                        "message": srs_message,
                    }
                )
            await asyncio.gather(*(track.enqueue_wav(wav) for track in list(self.audio_tracks)), return_exceptions=True)
        except Exception:
            logger.exception("Radio voice or SRS dispatch failed")
            await self.dashboard_events.broadcast(
                safe_error_event("TTS_SRS_FAILED", "Radio voice output failed. Check local Piper/SRS configuration.")
            )
        finally:
            if wav is not None:
                await asyncio.to_thread(self.radio_voice.cleanup_temp_wav, wav)

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
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--telemetry-host", default=None)
    parser.add_argument("--telemetry-port", type=int, default=None)
    parser.add_argument("--aircraft-profile", default="config/aircraft_profiles/default.json")
    parser.add_argument("--whisper-model")
    parser.add_argument("--whisper-engine", choices=["auto", "binding", "cli"], default=None)
    parser.add_argument("--whisper-cli-exe", default=None)
    parser.add_argument("--ptt-hotkey", default=None)
    parser.add_argument("--joystick-index", type=int, default=None)
    parser.add_argument("--joystick-button", type=int, default=None)
    parser.add_argument("--joystick-profile")
    parser.add_argument("--language", choices=["en", "zh", "ko", "fr", "ru", "es"])
    parser.add_argument("--personality", default="professional", choices=["professional", "conversational", "instructor", "rio"])
    parser.add_argument("--skin", default="default", choices=["default", "f16", "f18", "f15", "su27", "mig29", "su57", "f22"])
    parser.add_argument("--rwr-profile")
    parser.add_argument("--rwr-registry", default="config/rwr/adapters.json")
    parser.add_argument("--srs-config", default="config/srs/srs_audio.json")
    parser.add_argument("--disable-input-manager", action="store_true")
    parser.add_argument("--dashboard-token", help="Dashboard/API/WebSocket bearer token. Generated at startup when omitted.")
    parser.add_argument("--disable-dashboard-auth", action="store_true", help="Disable dashboard auth for local development only.")
    parser.add_argument("--allow-lan", action="store_true", help="Allow binding the dashboard bridge to non-local interfaces.")
    parser.add_argument("--allowed-origin", action="append", default=[], help="Additional allowed browser Origin. May be repeated.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    try:
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
            joystick_profile=args.joystick_profile,
            enable_input_manager=False if args.disable_input_manager else None,
            language=args.language,
            personality=args.personality,
            skin=args.skin,
            rwr_profile=args.rwr_profile,
            rwr_registry_path=args.rwr_registry,
            srs_config_path=args.srs_config,
            dashboard_token=args.dashboard_token,
            dashboard_auth_enabled=not args.disable_dashboard_auth,
            allow_lan=args.allow_lan,
            allowed_origins=tuple(args.allowed_origin),
        )
    except ValueError as exc:
        parser.error(str(exc))
    bridge.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
