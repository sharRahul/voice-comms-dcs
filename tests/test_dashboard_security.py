from __future__ import annotations

import pytest

from voice_comms_dcs.dashboard_security import DashboardSecurity, DashboardSecurityConfig


class FakeTransport:
    def __init__(self, host: str) -> None:
        self.host = host

    def get_extra_info(self, name: str) -> tuple[str, int] | None:
        if name == "peername":
            return (self.host, 12345)
        return None


class FakeRequest:
    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
        peer: str = "127.0.0.1",
    ) -> None:
        self.headers = headers or {}
        self.query = query or {}
        self.transport = FakeTransport(peer)


def test_generated_token_authenticates_correctly() -> None:
    security = DashboardSecurity(DashboardSecurityConfig())

    request = FakeRequest(headers={"Authorization": f"Bearer {security.token}"})

    assert security.is_authenticated_request(request)


def test_wrong_token_fails() -> None:
    security = DashboardSecurity(DashboardSecurityConfig(token="correct"))

    request = FakeRequest(headers={"X-Voice-Comms-DCS-Token": "wrong"})

    assert not security.is_authenticated_request(request)


def test_missing_token_fails_when_auth_enabled() -> None:
    security = DashboardSecurity(DashboardSecurityConfig(token="correct"))

    assert not security.is_authenticated_request(FakeRequest())


def test_query_token_can_be_disabled_for_api_routes() -> None:
    security = DashboardSecurity(DashboardSecurityConfig(token="correct"))
    request = FakeRequest(query={"token": "correct"})

    assert security.is_authenticated_request(request)
    assert not security.is_authenticated_request(request, allow_query=False)


def test_auth_disabled_only_allows_local_dev_mode() -> None:
    local_security = DashboardSecurity(DashboardSecurityConfig(auth_enabled=False))

    assert local_security.is_authenticated_request(FakeRequest(peer="127.0.0.1"))
    assert not local_security.is_authenticated_request(FakeRequest(peer="192.168.1.20"))

    with pytest.raises(ValueError):
        DashboardSecurity(
            DashboardSecurityConfig(host="0.0.0.0", auth_enabled=False, allow_lan=True)
        )


@pytest.mark.parametrize(
    "origin",
    ["http://127.0.0.1:8765", "http://localhost:8765"],
)
def test_origin_allowlist_accepts_localhost(origin: str) -> None:
    security = DashboardSecurity(DashboardSecurityConfig(port=8765))

    assert security.is_origin_allowed(FakeRequest(headers={"Origin": origin}))


def test_unknown_origin_rejected() -> None:
    security = DashboardSecurity(DashboardSecurityConfig(port=8765))

    assert not security.is_origin_allowed(FakeRequest(headers={"Origin": "https://example.com"}))


def test_absent_origin_accepted() -> None:
    security = DashboardSecurity(DashboardSecurityConfig(port=8765))

    assert security.is_origin_allowed(FakeRequest())
