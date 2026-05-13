from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Literal

Personality = Literal["professional", "conversational", "instructor", "rio"]
DashboardSkin = Literal["default", "f16", "f18", "f15", "su27", "mig29", "su57", "f22"]

VALID_PERSONALITIES: set[str] = {"professional", "conversational", "instructor", "rio"}
VALID_SKINS: set[str] = {"default", "f16", "f18", "f15", "su27", "mig29", "su57", "f22"}


@dataclass(frozen=True)
class DashboardSettingsSnapshot:
    personality: Personality = "professional"
    skin: DashboardSkin = "default"


class DashboardSettings:
    """Thread-safe runtime settings shared by the dashboard and Nimbus runtime."""

    def __init__(self, personality: str = "professional", skin: str = "default") -> None:
        self._lock = RLock()
        self._personality: Personality = _validate_personality(personality)
        self._skin: DashboardSkin = _validate_skin(skin)

    def snapshot(self) -> DashboardSettingsSnapshot:
        with self._lock:
            return DashboardSettingsSnapshot(personality=self._personality, skin=self._skin)

    def set_personality(self, personality: str) -> DashboardSettingsSnapshot:
        with self._lock:
            self._personality = _validate_personality(personality)
            return self.snapshot()

    def set_skin(self, skin: str) -> DashboardSettingsSnapshot:
        with self._lock:
            self._skin = _validate_skin(skin)
            return self.snapshot()


def _validate_personality(value: str) -> Personality:
    normalised = value.strip().lower()
    if normalised not in VALID_PERSONALITIES:
        raise ValueError(f"Unsupported personality: {value}")
    return normalised  # type: ignore[return-value]


def _validate_skin(value: str) -> DashboardSkin:
    normalised = value.strip().lower()
    if normalised not in VALID_SKINS:
        raise ValueError(f"Unsupported dashboard skin: {value}")
    return normalised  # type: ignore[return-value]


def personality_instruction(personality: str) -> str:
    """Instruction appended to the local LLM system prompt."""
    instructions = {
        "professional": "Use disciplined, professional tactical radio brevity. Avoid jokes and long explanations.",
        "conversational": "Use a natural wingman style. Stay concise but allow a little warmth when not in combat.",
        "instructor": "Act like a calm instructor pilot. Explain what matters and include short corrective coaching.",
        "rio": "Act like a back-seat RIO/WSO. Prioritise sensors, contacts, intercept geometry, and threat calls.",
    }
    return instructions.get(personality, instructions["professional"])
