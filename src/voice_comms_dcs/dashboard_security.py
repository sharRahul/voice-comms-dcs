from __future__ import annotations

import hmac
import json
import secrets
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from aiohttp import web

from .dashboard_settings import VALID_PERSONALITIES, VALID_SKINS
from .language_models import SUPPORTED_LANGUAGES

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_JSON_BYTES = 4096
MAX_WS_MESSAGE_CHARS = 70 * 1024
MAX_WS_TRANSCRIPT_CHARS = 500
MAX_WS_SDP_CHARS = 64 * 1024


class DashboardValidationError(ValueError):
    """Validation failure with a browser-safe error code and message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class DashboardSecurityConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str | None = None
    auth_enabled: bool = True
    allow_lan: bool = False
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)


class DashboardSecurity:
    """Small local dashboard auth and origin validation layer."""

    def __init__(self, config: DashboardSecurityConfig) -> None:
        self.config = config
        self._validate_bind_policy()
        self.token = config.token or (secrets.token_urlsafe(32) if config.auth_enabled else None)
        self.allowed_origins = self._build_allowed_origins()

    def _validate_bind_policy(self) -> None:
        if _normalise_host(self.config.host) not in LOCAL_HOSTS and not self.config.allow_lan:
            raise ValueError(
                "Refusing non-local dashboard bind without --allow-lan. "
                "Use --host 127.0.0.1 for local-only mode."
            )
        if _normalise_host(self.config.host) not in LOCAL_HOSTS and not self.config.auth_enabled:
            raise ValueError("Dashboard auth cannot be disabled when binding to LAN/non-local hosts.")

    def _build_allowed_origins(self) -> set[str]:
        origins = {
            f"http://127.0.0.1:{self.config.port}",
            f"http://localhost:{self.config.port}",
        }
        origins.update(origin.rstrip("/") for origin in self.config.allowed_origins if origin)
        return origins

    @property
    def auth_enabled(self) -> bool:
        return self.config.auth_enabled

    def dashboard_url(self) -> str:
        host = self.config.host if self.config.host not in {"0.0.0.0", "::"} else "127.0.0.1"
        base = f"http://{host}:{self.config.port}/dashboard"
        if self.auth_enabled and self.token:
            return f"{base}?{urlencode({'token': self.token})}"
        return base

    def extract_token(self, request: Any) -> str | None:
        auth_header = request.headers.get("Authorization", "")
        scheme, _, value = auth_header.partition(" ")
        if scheme.lower() == "bearer" and value:
            return value.strip()

        header_token = request.headers.get("X-Voice-Comms-DCS-Token")
        if header_token:
            return header_token.strip()

        query_token = request.query.get("token")
        if query_token:
            return str(query_token).strip()

        return None

    def is_authenticated_request(self, request: Any) -> bool:
        if not self.auth_enabled:
            return self.is_local_request(request)
        supplied = self.extract_token(request)
        if not supplied or not self.token:
            return False
        return hmac.compare_digest(supplied, self.token)

    def require_auth(self, request: Any) -> None:
        if not self.is_authenticated_request(request):
            raise web.HTTPUnauthorized(
                reason="Dashboard authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def is_origin_allowed(self, request: Any) -> bool:
        origin = request.headers.get("Origin")
        if not origin:
            return True
        return origin.rstrip("/") in self.allowed_origins

    def require_origin(self, request: Any) -> None:
        if not self.is_origin_allowed(request):
            raise web.HTTPForbidden(reason="Origin is not allowed")

    def require_request(self, request: Any, *, check_origin: bool = False) -> None:
        if check_origin:
            self.require_origin(request)
        self.require_auth(request)

    def is_local_request(self, request: Any) -> bool:
        transport = getattr(request, "transport", None)
        if transport is None:
            return True
        peer = transport.get_extra_info("peername")
        if not peer:
            return True
        host = peer[0] if isinstance(peer, tuple) and peer else str(peer)
        return _normalise_host(host) in LOCAL_HOSTS


async def read_json_object(request: web.Request, max_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    content_type = request.headers.get("Content-Type", "")
    if "application/json" not in content_type.lower():
        raise web.HTTPUnsupportedMediaType(reason="Content-Type must be application/json")

    content_length = request.content_length
    if content_length is not None and content_length > max_bytes:
        raise web.HTTPRequestEntityTooLarge(max_size=max_bytes, actual_size=content_length)

    body = await request.content.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise web.HTTPRequestEntityTooLarge(max_size=max_bytes, actual_size=len(body))
    return parse_json_object(body.decode("utf-8"), max_chars=max_bytes)


def parse_json_object(raw: str, *, max_chars: int = MAX_JSON_BYTES) -> dict[str, Any]:
    if len(raw) > max_chars:
        raise DashboardValidationError("PAYLOAD_TOO_LARGE", "JSON payload is too large")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DashboardValidationError("BAD_JSON", "Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise DashboardValidationError("BAD_JSON", "JSON payload must be an object")
    return payload


def validate_language_payload(payload: dict[str, Any]) -> str:
    language = str(payload.get("language", "en")).strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        raise DashboardValidationError("BAD_REQUEST", "Unsupported language")
    return language


def validate_settings_payload(payload: dict[str, Any]) -> dict[str, str]:
    changed: dict[str, str] = {}
    if "personality" in payload:
        personality = str(payload["personality"]).strip().lower()
        if personality not in VALID_PERSONALITIES:
            raise DashboardValidationError("BAD_REQUEST", "Unsupported personality")
        changed["personality"] = personality
    if "skin" in payload:
        skin = str(payload["skin"]).strip().lower()
        if skin not in VALID_SKINS:
            raise DashboardValidationError("BAD_REQUEST", "Unsupported dashboard skin")
        changed["skin"] = skin
    return changed


def validate_ws_message(raw: str) -> dict[str, Any]:
    payload = parse_json_object(raw, max_chars=MAX_WS_MESSAGE_CHARS)
    message_type = payload.get("type")
    if not isinstance(message_type, str):
        raise DashboardValidationError("BAD_REQUEST", "WebSocket message type is required")
    message_type = message_type.strip().lower()
    payload["type"] = message_type

    if message_type == "offer":
        sdp = payload.get("sdp")
        if not isinstance(sdp, str) or not sdp.strip():
            raise DashboardValidationError("BAD_REQUEST", "WebRTC offer SDP is required")
        if len(sdp) > MAX_WS_SDP_CHARS:
            raise DashboardValidationError("BAD_REQUEST", "WebRTC offer SDP is too large")
        return {"type": "offer", "sdp": sdp}

    if message_type == "transcript":
        text = payload.get("text")
        if not isinstance(text, str):
            raise DashboardValidationError("BAD_REQUEST", "Transcript text is required")
        text = text.strip()
        if len(text) > MAX_WS_TRANSCRIPT_CHARS:
            raise DashboardValidationError("BAD_REQUEST", "Transcript text is too large")
        return {"type": "transcript", "text": text}

    if message_type == "language":
        return {"type": "language", "language": validate_language_payload(payload)}

    if message_type == "settings":
        return {"type": "settings", **validate_settings_payload(payload)}

    if message_type in {"ptt_start", "ptt_stop", "ping"}:
        return {"type": message_type}

    raise DashboardValidationError("BAD_REQUEST", "Unknown WebSocket message type")


def safe_error_event(code: str, message: str) -> dict[str, str]:
    return {"type": "error", "code": code, "message": message}


def _normalise_host(host: str) -> str:
    return host.strip().strip("[]").lower()
