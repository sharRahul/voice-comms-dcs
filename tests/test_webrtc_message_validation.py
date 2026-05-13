from __future__ import annotations

import json

import pytest

from voice_comms_dcs.dashboard_security import (
    DashboardValidationError,
    MAX_WS_SDP_CHARS,
    validate_ws_message,
)


def test_valid_transcript() -> None:
    assert validate_ws_message('{"type": "transcript", "text": "request tanker"}') == {
        "type": "transcript",
        "text": "request tanker",
    }


def test_transcript_too_long_rejected() -> None:
    with pytest.raises(DashboardValidationError):
        validate_ws_message(json.dumps({"type": "transcript", "text": "x" * 501}))


def test_valid_language() -> None:
    assert validate_ws_message('{"type": "language", "language": "fr"}') == {
        "type": "language",
        "language": "fr",
    }


def test_unsupported_language_rejected() -> None:
    with pytest.raises(DashboardValidationError):
        validate_ws_message('{"type": "language", "language": "de"}')


def test_unknown_message_type_rejected() -> None:
    with pytest.raises(DashboardValidationError):
        validate_ws_message('{"type": "debug", "value": true}')


def test_malformed_json_rejected() -> None:
    with pytest.raises(DashboardValidationError):
        validate_ws_message('{"type": "ping"')


def test_oversized_sdp_rejected() -> None:
    with pytest.raises(DashboardValidationError):
        validate_ws_message(json.dumps({"type": "offer", "sdp": "v" * (MAX_WS_SDP_CHARS + 1)}))
