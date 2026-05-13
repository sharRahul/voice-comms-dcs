from __future__ import annotations

import asyncio

import pytest
from aiohttp import web

from voice_comms_dcs.dashboard_security import (
    DashboardValidationError,
    read_json_object,
    validate_language_payload,
    validate_settings_payload,
)


class FakeContent:
    def __init__(self, body: bytes) -> None:
        self.body = body

    async def read(self, _size: int) -> bytes:
        return self.body


class FakeRequest:
    def __init__(self, body: bytes, *, content_type: str = "application/json") -> None:
        self.headers = {"Content-Type": content_type}
        self.content_length = len(body)
        self.content = FakeContent(body)


def read_payload(body: bytes, *, max_bytes: int = 4096) -> dict[str, object]:
    return asyncio.run(read_json_object(FakeRequest(body), max_bytes=max_bytes))


def test_valid_json_object_accepted() -> None:
    assert read_payload(b'{"language": "en"}') == {"language": "en"}


def test_invalid_json_rejected() -> None:
    with pytest.raises(web.HTTPBadRequest):
        read_payload(b'{"language": ')


def test_array_json_rejected() -> None:
    with pytest.raises(web.HTTPBadRequest):
        read_payload(b'["en"]')


def test_oversized_json_rejected() -> None:
    with pytest.raises(web.HTTPRequestEntityTooLarge):
        read_payload(b'{"text": "too large"}', max_bytes=4)


def test_language_validation_rejects_unsupported_values() -> None:
    with pytest.raises(DashboardValidationError):
        validate_language_payload({"language": "de"})


def test_settings_validation_rejects_unsupported_personality_and_skin() -> None:
    with pytest.raises(DashboardValidationError):
        validate_settings_payload({"personality": "pirate"})

    with pytest.raises(DashboardValidationError):
        validate_settings_payload({"skin": "f35"})
