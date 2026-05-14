from __future__ import annotations

import copy
import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AiMode(str, Enum):
    NORMAL = "normal"
    COMBAT = "combat"


@dataclass(frozen=True)
class PriorityWarning:
    level: str
    message: str


@dataclass
class ConversationTurn:
    speaker: str
    text: str


@dataclass
class DynamicContext:
    telemetry: dict[str, Any] = field(default_factory=dict)
    mode: AiMode = AiMode.NORMAL
    warning: PriorityWarning | None = None
    prompt_prefix: str = ""


class ContextManager:
    """Builds the dynamic context window supplied to the local AI wingman.

    The context manager is deliberately deterministic. It converts DCS telemetry into a compact
    prompt prefix, tracks the conversation tail, and decides whether the AI should use normal or
    short tactical language.
    """

    def __init__(self, max_turns: int = 12, aircraft_profile: str = "DCS aircraft") -> None:
        self.max_turns = max_turns
        self.aircraft_profile = aircraft_profile
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self._last_context = DynamicContext()
        self._lock = threading.RLock()

    def update_telemetry(self, telemetry: dict[str, Any]) -> DynamicContext:
        telemetry_copy = copy.deepcopy(telemetry)
        mode = self._derive_mode(telemetry_copy)
        warning = self._derive_priority_warning(telemetry_copy)
        prompt_prefix = self._format_prompt_prefix(telemetry_copy, mode, warning)
        context = DynamicContext(
            telemetry=telemetry_copy,
            mode=mode,
            warning=warning,
            prompt_prefix=prompt_prefix,
        )
        with self._lock:
            self._last_context = context
            return copy.deepcopy(self._last_context)

    def get_context(self) -> DynamicContext:
        with self._lock:
            return copy.deepcopy(self._last_context)

    def add_turn(self, speaker: str, text: str) -> None:
        text = " ".join(text.strip().split())
        if text:
            with self._lock:
                self._turns.append(ConversationTurn(speaker=speaker, text=text))

    def build_llm_messages(self, pilot_text: str) -> list[dict[str, str]]:
        with self._lock:
            context = copy.deepcopy(self._last_context)
            turns = list(copy.deepcopy(self._turns))
            aircraft_profile = self.aircraft_profile

        mode_rule = (
            "You are in COMBAT MODE. Reply in ten words or fewer. Prioritise threats, RWR, "
            "missile warnings, fuel, altitude, and aircraft survival."
            if context.mode is AiMode.COMBAT
            else "You are in NORMAL MODE. Be concise, helpful, and use a calm wingman voice."
        )
        system = (
            "You are Nimbus, a local-first AI wingman/RIO/ATC assistant for DCS World. "
            "Never claim real-world authority. Never invent sensor data. Use only the supplied telemetry. "
            f"Aircraft profile: {aircraft_profile}. {mode_rule}\n\n"
            f"{context.prompt_prefix}"
        )
        messages = [{"role": "system", "content": system}]
        for turn in turns:
            role = "assistant" if turn.speaker == "assistant" else "user"
            messages.append({"role": role, "content": turn.text})
        messages.append({"role": "user", "content": pilot_text})
        return messages

    def _derive_mode(self, telemetry: dict[str, Any]) -> AiMode:
        g_load = _number_at(telemetry, "internal", "g_load")
        locked_range_nm = _number_at(telemetry, "tactical", "locked_target", "range_nm")
        if g_load is not None and g_load > 4.0:
            return AiMode.COMBAT
        if locked_range_nm is not None and locked_range_nm <= 10.0:
            return AiMode.COMBAT
        rwr_alerts = telemetry.get("tactical", {}).get("rwr_alerts", [])
        if isinstance(rwr_alerts, list) and any(_is_priority_rwr(alert) for alert in rwr_alerts):
            return AiMode.COMBAT
        return AiMode.NORMAL

    def _derive_priority_warning(self, telemetry: dict[str, Any]) -> PriorityWarning | None:
        rwr_alerts = telemetry.get("tactical", {}).get("rwr_alerts", [])
        if isinstance(rwr_alerts, list):
            for alert in rwr_alerts:
                if not isinstance(alert, dict):
                    continue
                threat = str(alert.get("threat_type", "unknown"))
                direction = str(alert.get("direction", "unknown"))
                severity = str(alert.get("severity", "")).lower()
                if severity in {"missile", "launch", "critical"}:
                    return PriorityWarning("critical", f"Missile/RWR threat {threat}, {direction}")

        fuel_total = _number_at(telemetry, "internal", "fuel_total_kg")
        if fuel_total is not None and fuel_total < 900:
            return PriorityWarning("high", f"Low fuel {fuel_total:.0f} kg")
        return None

    def _format_prompt_prefix(
        self,
        telemetry: dict[str, Any],
        mode: AiMode,
        warning: PriorityWarning | None,
    ) -> str:
        internal = telemetry.get("internal", {})
        spatial = telemetry.get("spatial", {})
        tactical = telemetry.get("tactical", {})
        locked = tactical.get("locked_target", {}) if isinstance(tactical, dict) else {}

        fields = [
            f"Mode: {mode.value.upper()}",
            _fmt("Alt ASL", _number_at(telemetry, "spatial", "altitude_asl_ft"), "ft"),
            _fmt("Alt AGL", _number_at(telemetry, "spatial", "altitude_agl_ft"), "ft"),
            _fmt("IAS", _number_at(telemetry, "spatial", "ias_kt"), "kt"),
            _fmt("Heading", _number_at(telemetry, "spatial", "heading_deg"), "deg"),
            _fmt("Fuel", _number_at(telemetry, "internal", "fuel_total_kg"), "kg"),
            _fmt("RPM L", _number_at(telemetry, "internal", "engine_rpm_left"), "%"),
            _fmt("RPM R", _number_at(telemetry, "internal", "engine_rpm_right"), "%"),
            _fmt("G", _number_at(telemetry, "internal", "g_load"), ""),
            f"Gear: {internal.get('gear', 'unknown')}",
            f"Flaps: {internal.get('flaps', 'unknown')}",
            _fmt("Locked range", _number_at(telemetry, "tactical", "locked_target", "range_nm"), "nm"),
            _fmt("Locked bearing", _number_at(telemetry, "tactical", "locked_target", "bearing_deg"), "deg"),
            _fmt("Locked velocity", _number_at(telemetry, "tactical", "locked_target", "velocity_kt"), "kt"),
        ]
        lat = spatial.get("lat")
        lon = spatial.get("lon")
        if lat is not None and lon is not None:
            fields.append(f"Position: {lat}, {lon}")
        if warning:
            fields.insert(1, f"Priority warning: {warning.message}")
        clean = [field for field in fields if field and not field.endswith("unknown")]
        return "[Context: " + "; ".join(clean) + "]"


def _number_at(data: dict[str, Any], *path: str) -> float | None:
    cursor: Any = data
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    try:
        if cursor is None:
            return None
        return float(cursor)
    except (TypeError, ValueError):
        return None


def _fmt(label: str, value: float | None, unit: str) -> str:
    if value is None:
        return ""
    if unit == "":
        return f"{label}: {value:.1f}"
    return f"{label}: {value:.0f} {unit}"


def _is_priority_rwr(alert: Any) -> bool:
    if not isinstance(alert, dict):
        return False
    severity = str(alert.get("severity", "")).lower()
    return severity in {"missile", "launch", "critical", "spike"}
