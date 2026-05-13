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

from .config import load_config
from .context_manager import ContextManager
from .nimbus_intelligence import NimbusIntelligence
from .radio_voice import RadioVoice
from .telemetry_listener import TelemetryListener

AUDIO_SAMPLE_RATE = 48000
AUDIO_FRAME_SAMPLES = 960  # 20 ms at 48 kHz


class EnergyVad:
    """Small local VAD fallback.

    This is intentionally dependency-light. Silero VAD can be added later behind the same
    `is_speech` method, but this simple gate already helps reject constant cockpit noise.
    """

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
    """Receives pilot WebRTC audio frames and exposes speech-gated PCM chunks."""

    def __init__(self, vad: EnergyVad | None = None) -> None:
        self.vad = vad or EnergyVad()
        self.queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=100)
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
            if not self.vad.is_speech(pcm):
                continue
            self.speech_frames += 1
            if self.queue.full():
                _ = self.queue.get_nowait()
            await self.queue.put(pcm)


class NimbusAudioTrack(AudioStreamTrack):
    """Outbound AI audio track.

    The track emits silence by default and can be fed WAV/PCM samples when Nimbus speaks.
    """

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
                    # Keep v0.2 dependency-light. Piper models can be configured for 48 kHz later;
                    # for now, simple linear resampling is good enough for radio feedback.
                    samples = linear_resample(samples, frame.sample_rate, AUDIO_SAMPLE_RATE)
                for chunk in chunk_audio(samples, AUDIO_FRAME_SAMPLES):
                    if self._queue.full():
                        _ = self._queue.get_nowait()
                    await self._queue.put(chunk)


class WebRtcBridge:
    """Local WebRTC + WebSocket signaling server for Phase 2.

    It is intentionally local-only by default. The server accepts WebRTC offers over `/ws`, receives
    pilot audio, returns a Nimbus outbound audio track, and accepts test transcript messages through
    a data channel or WebSocket while the STT integration is expanded.
    """

    def __init__(
        self,
        config_path: str,
        host: str = "127.0.0.1",
        port: int = 8765,
        telemetry_host: str = "127.0.0.1",
        telemetry_port: int = 10309,
    ) -> None:
        self.config_path = config_path
        self.host = host
        self.port = port
        self.context_manager = ContextManager(aircraft_profile="DCS aircraft")
        self.config = load_config(config_path)
        self.nimbus = NimbusIntelligence(self.config, context_manager=self.context_manager)
        self.radio_voice = RadioVoice()
        self.telemetry = TelemetryListener(
            host=telemetry_host,
            port=telemetry_port,
            on_telemetry=self.context_manager.update_telemetry,
        )
        self.peer_connections: set[RTCPeerConnection] = set()
        self.app = web.Application()
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/ws", self.websocket)

    async def index(self, _request: web.Request) -> web.Response:
        return web.Response(
            text="Voice-Comms-DCS Phase 2 WebRTC bridge is running. Connect signaling to /ws.",
            content_type="text/plain",
        )

    async def health(self, _request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "peers": len(self.peer_connections),
                "telemetry_age_seconds": self.telemetry.latest().age_seconds,
                "context": self.context_manager.get_context().prompt_prefix,
            }
        )

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        pc = RTCPeerConnection()
        outbound_audio = NimbusAudioTrack()
        inbound_audio = InboundAudioSink()
        pc.addTrack(outbound_audio)
        self.peer_connections.add(pc)

        @pc.on("track")
        def on_track(track: MediaStreamTrack) -> None:
            if track.kind == "audio":
                asyncio.create_task(inbound_audio.consume(track))

        @pc.on("datachannel")
        def on_datachannel(channel: Any) -> None:
            @channel.on("message")
            def on_message(message: str) -> None:
                asyncio.create_task(
                    self._handle_text_message(str(message), outbound_audio, channel.send)
                )

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
                    await ws.send_json(
                        {
                            "type": pc.localDescription.type,
                            "sdp": pc.localDescription.sdp,
                        }
                    )
                elif message_type == "transcript":
                    await self._handle_text_message(
                        str(payload.get("text", "")),
                        outbound_audio,
                        lambda text: asyncio.create_task(ws.send_json({"type": "nimbus", "text": text})),
                    )
                elif message_type == "ping":
                    await ws.send_json({"type": "pong", "time": time.time()})
        finally:
            self.peer_connections.discard(pc)
            await pc.close()
        return ws

    async def _handle_text_message(
        self,
        text: str,
        outbound_audio: NimbusAudioTrack,
        reply: Any,
    ) -> None:
        text = text.strip()
        if not text:
            return
        decision, dispatch = self.nimbus.handle_pilot_text(text)
        response = decision.response_text
        maybe_reply = reply(response)
        if asyncio.iscoroutine(maybe_reply):
            await maybe_reply
        try:
            wav = self.radio_voice.synthesise_to_temp_wav(response)
            await outbound_audio.enqueue_wav(wav)
        except Exception:
            # TTS should not break signaling or command dispatch.
            pass

    def run(self) -> None:
        self.telemetry.start()
        web.run_app(self.app, host=self.host, port=self.port)

    async def close(self) -> None:
        self.telemetry.stop()
        self.nimbus.close()
        await asyncio.gather(*(pc.close() for pc in self.peer_connections), return_exceptions=True)
        self.peer_connections.clear()


def audio_frame_to_float_mono(frame: av.AudioFrame) -> np.ndarray:
    array = frame.to_ndarray()
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
    args = parser.parse_args(argv)

    bridge = WebRtcBridge(
        config_path=args.config,
        host=args.host,
        port=args.port,
        telemetry_host=args.telemetry_host,
        telemetry_port=args.telemetry_port,
    )
    bridge.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
