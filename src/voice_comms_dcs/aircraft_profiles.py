from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AircraftProfile:
    id: str
    display_name: str
    role: str = "wingman"
    callsign: str = "Nimbus"
    notes: str = ""
    brevity_style: str = "modern NATO tactical"
    reserved_voice_flags: tuple[int, int] = (5100, 5199)
    extra: dict[str, Any] = field(default_factory=dict)

    def prompt_identity(self) -> str:
        return (
            f"{self.callsign}, {self.role} for {self.display_name}. "
            f"Use {self.brevity_style} brevity. {self.notes}"
        ).strip()


def load_aircraft_profile(path: str | Path | None) -> AircraftProfile:
    if path is None:
        return AircraftProfile(id="default", display_name="DCS aircraft")

    profile_path = Path(path)
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    flags = data.get("reserved_voice_flags", [5100, 5199])
    return AircraftProfile(
        id=str(data.get("id", profile_path.stem)),
        display_name=str(data.get("display_name", "DCS aircraft")),
        role=str(data.get("role", "wingman")),
        callsign=str(data.get("callsign", "Nimbus")),
        notes=str(data.get("notes", "")),
        brevity_style=str(data.get("brevity_style", "modern NATO tactical")),
        reserved_voice_flags=(int(flags[0]), int(flags[1])) if isinstance(flags, list) and len(flags) == 2 else (5100, 5199),
        extra={k: v for k, v in data.items() if k not in {
            "id",
            "display_name",
            "role",
            "callsign",
            "notes",
            "brevity_style",
            "reserved_voice_flags",
        }},
    )
