from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
import requests

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
from voice_comms_dcs.context_manager import ContextManager
from voice_comms_dcs.nimbus_intelligence import (
    DEFAULT_LLM_TIMEOUT_SECONDS,
    OLLAMA_UNAVAILABLE_RESPONSE,
    IntentType,
    LocalLlmClient,
    NimbusIntelligence,
    OllamaUnavailableError,
)


class _NoopCommandService:
    def close(self) -> None:
        return None


class _OfflineLlm:
    def chat_text(self, messages: list[dict[str, str]], combat_mode: bool = False) -> str:
        raise OllamaUnavailableError("offline")


class _StaticLlm:
    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: list[dict[str, str]] | None = None

    def chat_text(self, messages: list[dict[str, str]], combat_mode: bool = False) -> str:
        self.messages = messages
        return self.response


def _config(**overrides: Any) -> AppConfig:
    base = AppConfig(
        dcs_host="127.0.0.1",
        dcs_port=10308,
        min_confidence=0.90,
        language=LanguageConfig(selected="en", installed=("en",)),
        telemetry=TelemetryConfig(),
        webrtc=WebRtcConfig(),
        input=InputConfig(),
        push_to_talk=PushToTalkConfig(),
        udp_reliability=UdpReliabilityConfig(enabled=False),
        dashboard_privacy=DashboardPrivacyConfig(),
        stt=SttConfig(),
        llm=LlmConfig(timeout_seconds=DEFAULT_LLM_TIMEOUT_SECONDS),
        tts=TtsConfig(),
        commands=(
            VoiceCommand(
                id="request_tanker",
                phrases=("request tanker",),
                action=Action(type="flag", flag=5101, value=1),
            ),
        ),
    )
    return replace(base, **overrides)


def _nimbus(llm: Any) -> NimbusIntelligence:
    instance = NimbusIntelligence(
        config=_config(),
        context_manager=ContextManager(max_turns=50),
        llm=llm,
    )
    instance.command_service = _NoopCommandService()  # type: ignore[assignment]
    return instance


def test_local_llm_client_uses_environment_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIMBUS_LLM_TIMEOUT", "1.25")

    client = LocalLlmClient(timeout_seconds=DEFAULT_LLM_TIMEOUT_SECONDS)

    assert client.timeout_seconds == 1.25


def test_local_llm_client_raises_offline_error_on_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_connection_error(*_args: Any, **_kwargs: Any) -> None:
        raise requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr("voice_comms_dcs.nimbus_intelligence.requests.post", raise_connection_error)
    client = LocalLlmClient(timeout_seconds=0.01)

    with pytest.raises(OllamaUnavailableError):
        client.chat_text([{"role": "user", "content": "status"}])


def test_unrecognised_query_returns_offline_notice_when_ollama_is_unavailable() -> None:
    nimbus = _nimbus(_OfflineLlm())

    decision, dispatch = nimbus.handle_pilot_text("Nimbus, can you brief the picture?")

    assert dispatch is None
    assert decision.intent is IntentType.CONVERSATIONAL
    assert decision.response_text == OLLAMA_UNAVAILABLE_RESPONSE


def test_context_window_tokens_and_trim_keep_recent_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nimbus = _nimbus(_StaticLlm("roger"))
    for index in range(12):
        nimbus.context_manager.add_turn("user", f"old user turn {index} with many words")
        nimbus.context_manager.add_turn("assistant", f"old assistant turn {index} with many words")

    assert nimbus.context_window_tokens > 0

    monkeypatch.setenv("NIMBUS_CONTEXT_LIMIT", "30")
    nimbus.trim_history_if_needed()
    messages = nimbus.context_manager.build_llm_messages("latest status")
    history_text = "\n".join(message["content"] for message in messages)

    assert nimbus.context_window_tokens <= 30
    assert "old user turn 0" not in history_text
    assert "old assistant turn 11" in history_text


def test_telemetry_context_is_system_message_not_history() -> None:
    llm = _StaticLlm("Telemetry acknowledged")
    nimbus = _nimbus(llm)
    nimbus.update_telemetry(
        {
            "internal": {"fuel_total_kg": 2500},
            "spatial": {"altitude_asl_ft": 12000, "ias_kt": 320},
        }
    )

    decision, _dispatch = nimbus.handle_pilot_text("Nimbus, what do you think?")

    assert decision.response_text == "Telemetry acknowledged"
    assert llm.messages is not None
    assert llm.messages[0]["role"] == "system"
    assert "Fuel: 2500 kg" in llm.messages[0]["content"]
    assert all("Fuel: 2500 kg" not in message["content"] for message in llm.messages[1:])
