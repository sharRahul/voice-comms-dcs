from __future__ import annotations

from voice_comms_dcs.app import VoiceCommsService
from voice_comms_dcs.config import (
    Action,
    AppConfig,
    DashboardPrivacyConfig,
    InputConfig,
    LanguageConfig,
    LlmConfig,
    PushToTalkConfig,
    SttConfig,
    TelemetryConfig,
    TtsConfig,
    UdpReliabilityConfig,
    VoiceCommand,
    WebRtcConfig,
)
from voice_comms_dcs.matcher import MatchResult, find_best_match


def _config() -> AppConfig:
    commands = (VoiceCommand("request_tanker", ("request tanker",), Action("flag", flag=5101, value=1)),)
    return AppConfig(
        dcs_host="127.0.0.1",
        dcs_port=10308,
        min_confidence=0.78,
        language=LanguageConfig(),
        telemetry=TelemetryConfig(),
        webrtc=WebRtcConfig(),
        input=InputConfig(),
        push_to_talk=PushToTalkConfig(),
        udp_reliability=UdpReliabilityConfig(enabled=False),
        dashboard_privacy=DashboardPrivacyConfig(),
        stt=SttConfig(),
        llm=LlmConfig(),
        tts=TtsConfig(),
        commands=commands,
    )


class FakeClient:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send_command(self, command: VoiceCommand) -> str:
        self.sent.append(command.id)
        return f"sent:{command.id}"

    def close(self) -> None:
        pass


def test_dispatch_match_sends_without_rematching():
    service = VoiceCommsService(_config())
    fake = FakeClient()
    service.client.close()
    service.client = fake  # type: ignore[assignment]

    class FailingMatcher:
        def find_best_match(self, *_args, **_kwargs):
            raise AssertionError("matcher should not be called by dispatch_match")

    service.matcher = FailingMatcher()  # type: ignore[assignment]
    command = service.config.commands[0]
    match = MatchResult(command=command, phrase="request tanker", confidence=1.0, transcript="request tanker")
    result = service.dispatch_match("request tanker", match)
    assert result.matched is True
    assert result.payload == "sent:request_tanker"
    assert fake.sent == ["request_tanker"]


def test_handle_transcript_remains_backward_compatible():
    service = VoiceCommsService(_config())
    fake = FakeClient()
    service.client.close()
    service.client = fake  # type: ignore[assignment]
    result = service.handle_transcript("request tanker")
    assert result.matched is True
    assert result.match is not None
    assert result.match.command.id == "request_tanker"
    assert result.payload == "sent:request_tanker"


def test_handle_transcript_reuses_nimbus_precomputed_match():
    service = VoiceCommsService(_config())
    fake = FakeClient()
    service.client.close()
    service.client = fake  # type: ignore[assignment]

    precomputed = find_best_match("request tanker", service.config.commands, service.config.min_confidence)
    assert precomputed is not None

    class FailingMatcher:
        def find_best_match(self, *_args, **_kwargs):
            raise AssertionError("cached Nimbus match should be consumed")

    service.matcher = FailingMatcher()  # type: ignore[assignment]
    result = service.handle_transcript("request tanker")
    assert result.matched is True
    assert result.match == precomputed
    assert fake.sent == ["request_tanker"]
