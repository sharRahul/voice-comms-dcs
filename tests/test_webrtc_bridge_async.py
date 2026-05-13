from __future__ import annotations

import asyncio
import time
from types import MethodType, SimpleNamespace

from voice_comms_dcs.webrtc_bridge import WebRtcBridge


class FakeEvents:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def broadcast(self, event: dict[str, object]) -> None:
        self.events.append(event)


class FakeSettings:
    def snapshot(self) -> SimpleNamespace:
        return SimpleNamespace(personality="professional", skin="default")


class SlowNimbus:
    def handle_pilot_text(self, text: str) -> tuple[SimpleNamespace, None]:
        time.sleep(0.08)
        return (
            SimpleNamespace(
                response_text=f"copy {text}",
                intent=SimpleNamespace(value="conversational"),
                command_id=None,
            ),
            None,
        )


class RaisingNimbus:
    def handle_pilot_text(self, _text: str) -> tuple[SimpleNamespace, None]:
        raise RuntimeError("C:\\secret\\ollama failed")


def make_bridge(nimbus: object) -> WebRtcBridge:
    bridge = WebRtcBridge.__new__(WebRtcBridge)
    bridge.nimbus = nimbus
    bridge.dashboard_events = FakeEvents()
    bridge.current_language = "en"
    bridge.settings = FakeSettings()
    bridge._llm_semaphore = asyncio.Semaphore(1)
    bridge._llm_timeout_seconds = 1.0
    bridge.audio_tracks = set()

    async def no_speak(_self: WebRtcBridge, _response: str) -> None:
        return None

    bridge._speak_response = MethodType(no_speak, bridge)
    return bridge


def test_process_transcript_uses_thread_without_blocking_event_loop() -> None:
    async def run() -> None:
        bridge = make_bridge(SlowNimbus())
        ticks = 0
        done = False

        async def ticker() -> None:
            nonlocal ticks
            while not done:
                ticks += 1
                await asyncio.sleep(0.01)

        ticker_task = asyncio.create_task(ticker())
        await bridge._process_transcript("request picture", None)
        done = True
        await ticker_task

        assert ticks > 1
        assert any(event.get("type") == "conversation" for event in bridge.dashboard_events.events)

    asyncio.run(run())


def test_process_transcript_broadcasts_sanitized_error_when_nimbus_raises() -> None:
    async def run() -> None:
        bridge = make_bridge(RaisingNimbus())

        await bridge._process_transcript("hello", None)

        assert bridge.dashboard_events.events == [
            {
                "type": "error",
                "code": "NIMBUS_FAILED",
                "message": "Nimbus processing failed. Check local model configuration.",
            }
        ]

    asyncio.run(run())
