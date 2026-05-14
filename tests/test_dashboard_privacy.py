from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from voice_comms_dcs.api_routes import _redact_event, _snapshot
from voice_comms_dcs.config import DashboardPrivacyConfig


@dataclass
class Latest:
    age_seconds: float
    data: dict


class FakeTelemetry:
    def latest(self):
        return Latest(age_seconds=0.1, data={})


class FakeContextManager:
    def __init__(self, telemetry):
        self.telemetry = telemetry

    def get_context(self):
        return SimpleNamespace(
            telemetry=self.telemetry,
            mode=SimpleNamespace(value="normal"),
            warning=None,
            prompt_prefix="precise tactical context",
        )


def _telemetry():
    return {
        "aircraft": {"type": "F-16C"},
        "internal": {"fuel_total_kg": 3000},
        "spatial": {"lat": 1.0, "lon": 2.0, "x": 3.0, "y": 4.0, "z": 5.0, "ias_kt": 350},
        "tactical": {"locked_target": {"bearing_deg": 120}},
    }


def _ptt():
    return {
        "last_transcript": "request tanker",
        "whisper_model": "C:/models/whisper/ggml-base.en.bin",
    }


def test_default_snapshot_redacts_position_and_model_path():
    snapshot = _snapshot(FakeContextManager(_telemetry()), FakeTelemetry(), _ptt)
    assert "lat" not in snapshot["spatial"]
    assert "lon" not in snapshot["spatial"]
    assert "x" not in snapshot["spatial"]
    assert snapshot["spatial"]["ias_kt"] == 350
    assert snapshot["ptt"]["whisper_model"] == "ggml-base.en.bin"


def test_opt_in_exposes_position_and_context():
    snapshot = _snapshot(
        FakeContextManager(_telemetry()),
        FakeTelemetry(),
        _ptt,
        privacy=DashboardPrivacyConfig(expose_position=True, expose_model_paths=True),
    )
    assert snapshot["spatial"]["lat"] == 1.0
    assert snapshot["spatial"]["x"] == 3.0
    assert snapshot["context"] == "precise tactical context"
    assert snapshot["ptt"]["whisper_model"].endswith("ggml-base.en.bin")


def test_privacy_can_hide_tactical_context_and_last_transcript():
    snapshot = _snapshot(
        FakeContextManager(_telemetry()),
        FakeTelemetry(),
        _ptt,
        privacy=DashboardPrivacyConfig(
            expose_tactical=False,
            expose_context=False,
            expose_last_transcript=False,
        ),
    )
    assert snapshot["tactical"] == {}
    assert snapshot["context"] == ""
    assert "last_transcript" not in snapshot["ptt"]


def test_ptt_broadcast_redacts_model_path_and_transcript_when_configured():
    event = {"type": "ptt", "state": _ptt()}
    redacted = _redact_event(event, DashboardPrivacyConfig(expose_last_transcript=False))
    assert redacted["state"]["whisper_model"] == "ggml-base.en.bin"
    assert "last_transcript" not in redacted["state"]


def test_transcript_broadcast_can_be_redacted():
    event = {"type": "transcript", "text": "request tanker"}
    redacted = _redact_event(event, DashboardPrivacyConfig(expose_last_transcript=False))
    assert redacted["text"] == "[redacted]"
