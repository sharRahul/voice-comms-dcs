from __future__ import annotations

import asyncio
import json
import logging
from importlib import resources
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from .config import DashboardPrivacyConfig
from .dashboard_security import (
    DashboardSecurity,
    DashboardValidationError,
    read_json_object,
    validate_language_payload,
    validate_settings_payload,
)
from .input_profiles import presets_as_api_payload
from .language_models import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)


class DashboardEventHub:
    """Broadcasts lightweight dashboard events to connected local web clients."""

    def __init__(self, send_timeout_seconds: float = 1.0) -> None:
        self.send_timeout_seconds = max(0.05, float(send_timeout_seconds))
        self.privacy: DashboardPrivacyConfig | None = None
        self._clients: set[web.WebSocketResponse] = set()
        self._lock = asyncio.Lock()
        self.privacy: DashboardPrivacyConfig | None = None

    async def connect(self, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def _send_one(self, ws: web.WebSocketResponse, message: str) -> bool:
        try:
            await asyncio.wait_for(ws.send_str(message), timeout=self.send_timeout_seconds)
            return True
        except Exception:
            await self.disconnect(ws)
            logger.debug("dashboard_client_send_failed", exc_info=True)
            return False

    async def broadcast(self, event: dict[str, Any]) -> None:
        if isinstance(self.privacy, DashboardPrivacyConfig):
            event = _redact_event(event, self.privacy)
        message = json.dumps(event, default=str, ensure_ascii=False)
        async with self._lock:
            clients = list(self._clients)
        if not clients:
            return
        await asyncio.gather(
            *(self._send_one(ws, message) for ws in clients),
            return_exceptions=True,
        )


def setup_dashboard_routes(
    app: web.Application,
    *,
    context_manager: Any,
    telemetry_listener: Any,
    event_hub: DashboardEventHub,
    ptt_state_provider: Any,
    language_provider: Any | None = None,
    language_setter: Any | None = None,
    settings_provider: Any | None = None,
    personality_setter: Any | None = None,
    skin_setter: Any | None = None,
    joystick_preset_setter: Any | None = None,
    security: DashboardSecurity | None = None,
    privacy: DashboardPrivacyConfig | None = None,
) -> None:
    """Attach local-only dashboard routes to the aiohttp app."""

    def require_auth(
        request: web.Request,
        *,
        check_origin: bool = False,
        allow_query: bool = False,
    ) -> None:
        if security is not None:
            security.require_request(request, check_origin=check_origin, allow_query=allow_query)

    resolved_privacy = _resolve_privacy(privacy, ptt_state_provider, context_manager)
    event_hub.privacy = resolved_privacy

    def snapshot() -> dict[str, Any]:
        return _snapshot(
            context_manager,
            telemetry_listener,
            ptt_state_provider,
            language_provider,
            settings_provider,
            privacy=resolved_privacy,
        )

    async def dashboard(request: web.Request) -> web.Response:
        require_auth(request, allow_query=True)
        html = _read_web_asset("index.html")
        return web.Response(text=html, content_type="text/html")

    async def asset(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if "/" in name or "\\" in name or name.startswith("."):
            raise web.HTTPNotFound()
        content = _read_web_asset(name)
        content_type = "text/plain"
        if name.endswith(".js"):
            content_type = "application/javascript"
        elif name.endswith(".css"):
            content_type = "text/css"
        elif name.endswith(".html"):
            content_type = "text/html"
        return web.Response(text=content, content_type=content_type)

    async def i18n(request: web.Request) -> web.Response:
        language = request.match_info["language"].lower()
        if language not in SUPPORTED_LANGUAGES:
            language = "en"
        return web.json_response(_read_i18n(language), dumps=lambda data: json.dumps(data, ensure_ascii=False))

    async def status(request: web.Request) -> web.Response:
        require_auth(request)
        return web.json_response(
            snapshot(),
            dumps=lambda data: json.dumps(data, ensure_ascii=False),
        )

    async def set_language(request: web.Request) -> web.Response:
        require_auth(request, check_origin=True)
        payload = await read_json_object(request)
        try:
            language = validate_language_payload(payload)
        except DashboardValidationError as exc:
            raise web.HTTPBadRequest(reason=exc.safe_message) from exc
        if callable(language_setter):
            language_setter(language)
        await event_hub.broadcast({"type": "language", "language": language})
        return web.json_response({"language": language})

    async def set_settings(request: web.Request) -> web.Response:
        require_auth(request, check_origin=True)
        payload = await read_json_object(request)
        try:
            changed = validate_settings_payload(payload)
        except DashboardValidationError as exc:
            raise web.HTTPBadRequest(reason=exc.safe_message) from exc
        if "personality" in changed:
            if callable(personality_setter):
                personality_setter(changed["personality"])
        if "skin" in changed:
            if callable(skin_setter):
                skin_setter(changed["skin"])
        await event_hub.broadcast({"type": "settings", **changed})
        return web.json_response(changed, dumps=lambda data: json.dumps(data, ensure_ascii=False))

    async def joystick_presets(request: web.Request) -> web.Response:
        require_auth(request)
        return web.json_response(presets_as_api_payload(), dumps=lambda data: json.dumps(data, ensure_ascii=False))

    async def set_joystick_preset(request: web.Request) -> web.Response:
        require_auth(request, check_origin=True)
        payload = await read_json_object(request)
        profile_id = str(payload.get("profile_id", ""))
        if not profile_id:
            raise web.HTTPBadRequest(reason="profile_id is required")
        if not callable(joystick_preset_setter):
            raise web.HTTPServiceUnavailable(reason="joystick preset setter is not available")
        try:
            preset = joystick_preset_setter(profile_id)
        except ValueError as exc:
            raise web.HTTPBadRequest(reason=str(exc)) from exc
        response = {
            "profile_id": preset.id,
            "label": preset.label,
            "joystick_index": preset.joystick_index,
            "button_index": preset.button_index,
            "hotkey": preset.hotkey,
        }
        await event_hub.broadcast({"type": "joystick_preset", **response})
        return web.json_response(response, dumps=lambda data: json.dumps(data, ensure_ascii=False))

    async def live_ws(request: web.Request) -> web.WebSocketResponse:
        require_auth(request, check_origin=True, allow_query=True)
        ws = web.WebSocketResponse(heartbeat=15.0)
        await ws.prepare(request)
        await event_hub.connect(ws)
        try:
            await ws.send_json(
                {
                    "type": "status",
                    "payload": snapshot(),
                }
            )
            while True:
                try:
                    await ws.send_json(
                        {
                            "type": "status",
                            "payload": snapshot(),
                        }
                    )
                    message = await asyncio.wait_for(ws.receive(), timeout=0.75)
                    if message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                        break
                except asyncio.TimeoutError:
                    continue
        finally:
            await event_hub.disconnect(ws)
        return ws

    app.router.add_get("/dashboard", dashboard)
    app.router.add_get("/web_ui/{name}", asset)
    app.router.add_get("/api/i18n/{language}", i18n)
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/language", set_language)
    app.router.add_post("/api/settings", set_settings)
    app.router.add_get("/api/joystick-presets", joystick_presets)
    app.router.add_post("/api/joystick-preset", set_joystick_preset)
    app.router.add_get("/api/live", live_ws)


def _resolve_privacy(
    privacy: DashboardPrivacyConfig | None,
    ptt_state_provider: Any,
    context_manager: Any,
) -> DashboardPrivacyConfig:
    if privacy is not None:
        return privacy
    for candidate in (getattr(ptt_state_provider, "__self__", None), context_manager):
        config = getattr(candidate, "config", None)
        configured = getattr(config, "dashboard_privacy", None)
        if isinstance(configured, DashboardPrivacyConfig):
            return configured
    return DashboardPrivacyConfig()


def _snapshot(
    context_manager: Any,
    telemetry_listener: Any,
    ptt_state_provider: Any,
    language_provider: Any | None = None,
    settings_provider: Any | None = None,
    *,
    privacy: DashboardPrivacyConfig | None = None,
) -> dict[str, Any]:
    privacy = privacy or DashboardPrivacyConfig()
    latest = telemetry_listener.latest()
    context = context_manager.get_context()
    ptt_state = _redact_ptt_state(
        ptt_state_provider() if callable(ptt_state_provider) else {},
        privacy,
    )
    telemetry = context.telemetry or latest.data or {}
    language = language_provider() if callable(language_provider) else "en"
    settings = settings_provider() if callable(settings_provider) else {"personality": "professional", "skin": "default"}
    if hasattr(settings, "__dict__"):
        settings = settings.__dict__
    spatial = dict(telemetry.get("spatial", {}))
    if not privacy.expose_position:
        _redact_position(spatial)
    tactical = dict(telemetry.get("tactical", {})) if privacy.expose_tactical else {}
    context_text = context.prompt_prefix if privacy.expose_context else ""
    return {
        "telemetry_age_seconds": latest.age_seconds,
        "language": language,
        "available_languages": SUPPORTED_LANGUAGES,
        "settings": settings,
        "ptt": ptt_state,
        "mode": getattr(context.mode, "value", str(context.mode)),
        "warning": context.warning.message if context.warning else None,
        "context": context_text,
        "aircraft": telemetry.get("aircraft", {}),
        "internal": telemetry.get("internal", {}),
        "spatial": spatial,
        "tactical": tactical,
    }


def _redact_event(event: dict[str, Any], privacy: DashboardPrivacyConfig) -> dict[str, Any]:
    if event.get("type") == "ptt" and isinstance(event.get("state"), dict):
        redacted = dict(event)
        redacted["state"] = _redact_ptt_state(redacted["state"], privacy)
        return redacted
    if event.get("type") == "transcript" and not privacy.expose_last_transcript:
        redacted = dict(event)
        redacted["text"] = "[redacted]"
        return redacted
    return event


def _redact_position(spatial: dict[str, Any]) -> None:
    for key in ("lat", "lon", "latitude", "longitude", "x", "y", "z"):
        spatial.pop(key, None)


def _redact_ptt_state(ptt_state: Any, privacy: DashboardPrivacyConfig) -> dict[str, Any]:
    if not isinstance(ptt_state, dict):
        return {}
    redacted = dict(ptt_state)
    if not privacy.expose_last_transcript:
        redacted.pop("last_transcript", None)
    if not privacy.expose_model_paths and "whisper_model" in redacted:
        model = redacted.get("whisper_model")
        redacted["whisper_model"] = Path(str(model)).name if model else None
    return redacted


def _read_web_asset(name: str) -> str:
    package = resources.files("voice_comms_dcs").joinpath("web_ui", name)
    return package.read_text(encoding="utf-8")


def _read_i18n(language: str) -> dict[str, str]:
    candidates = [
        Path("config") / "i18n" / f"{language}.json",
        Path(__file__).resolve().parents[2] / "config" / "i18n" / f"{language}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    if language != "en":
        return _read_i18n("en")
    return {"language": "English"}
