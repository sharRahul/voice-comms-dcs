from __future__ import annotations

import asyncio
import json
from importlib import resources
from typing import Any

from aiohttp import WSMsgType, web


class DashboardEventHub:
    """Broadcasts lightweight dashboard events to connected local web clients."""

    def __init__(self) -> None:
        self._clients: set[web.WebSocketResponse] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        message = json.dumps(event, default=str)
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_str(message)
            except Exception:
                await self.disconnect(ws)


def setup_dashboard_routes(
    app: web.Application,
    *,
    context_manager: Any,
    telemetry_listener: Any,
    event_hub: DashboardEventHub,
    ptt_state_provider: Any,
) -> None:
    """Attach local-only dashboard routes to the aiohttp app."""

    async def dashboard(_request: web.Request) -> web.Response:
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

    async def status(_request: web.Request) -> web.Response:
        return web.json_response(_snapshot(context_manager, telemetry_listener, ptt_state_provider))

    async def live_ws(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=15.0)
        await ws.prepare(request)
        await event_hub.connect(ws)
        try:
            await ws.send_json(
                {
                    "type": "status",
                    "payload": _snapshot(context_manager, telemetry_listener, ptt_state_provider),
                }
            )
            while True:
                try:
                    await ws.send_json(
                        {
                            "type": "status",
                            "payload": _snapshot(context_manager, telemetry_listener, ptt_state_provider),
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
    app.router.add_get("/api/status", status)
    app.router.add_get("/api/live", live_ws)


def _snapshot(context_manager: Any, telemetry_listener: Any, ptt_state_provider: Any) -> dict[str, Any]:
    latest = telemetry_listener.latest()
    context = context_manager.get_context()
    ptt_state = ptt_state_provider() if callable(ptt_state_provider) else {}
    telemetry = latest.data or {}
    return {
        "telemetry_age_seconds": latest.age_seconds,
        "ptt": ptt_state,
        "mode": getattr(context.mode, "value", str(context.mode)),
        "warning": context.warning.message if context.warning else None,
        "context": context.prompt_prefix,
        "aircraft": telemetry.get("aircraft", {}),
        "internal": telemetry.get("internal", {}),
        "spatial": telemetry.get("spatial", {}),
        "tactical": telemetry.get("tactical", {}),
    }


def _read_web_asset(name: str) -> str:
    package = resources.files("voice_comms_dcs").joinpath("web_ui", name)
    return package.read_text(encoding="utf-8")
