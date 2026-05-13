from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RwrThreatMapping:
    symbol: str
    label: str
    threat_type: str
    severity: str = "search"


@dataclass(frozen=True)
class RwrAdapterProfile:
    id: str
    label: str
    aircraft: tuple[str, ...] = field(default_factory=tuple)
    mappings: dict[str, RwrThreatMapping] = field(default_factory=dict)


DEFAULT_SEVERITY_ORDER = {
    "unknown": 0,
    "search": 1,
    "track": 2,
    "spike": 3,
    "launch": 4,
    "missile": 5,
    "critical": 6,
}


class RwrAdapterRegistry:
    """Normalises aircraft-specific RWR symbols into Nimbus threat fields."""

    def __init__(self, profiles: dict[str, RwrAdapterProfile]) -> None:
        self.profiles = profiles

    @classmethod
    def from_json(cls, path: str | Path = "config/rwr/adapters.json") -> "RwrAdapterRegistry":
        file_path = Path(path)
        if not file_path.exists():
            file_path = Path(__file__).resolve().parents[2] / "config" / "rwr" / "adapters.json"
        data = json.loads(file_path.read_text(encoding="utf-8"))
        profiles: dict[str, RwrAdapterProfile] = {}
        for raw in data.get("profiles", []):
            mappings: dict[str, RwrThreatMapping] = {}
            for symbol, mapping in raw.get("mappings", {}).items():
                mappings[str(symbol).upper()] = RwrThreatMapping(
                    symbol=str(symbol).upper(),
                    label=str(mapping.get("label", symbol)),
                    threat_type=str(mapping.get("threat_type", "unknown")),
                    severity=str(mapping.get("severity", "search")).lower(),
                )
            profile = RwrAdapterProfile(
                id=str(raw["id"]),
                label=str(raw.get("label", raw["id"])),
                aircraft=tuple(str(item).lower() for item in raw.get("aircraft", [])),
                mappings=mappings,
            )
            profiles[profile.id] = profile
        return cls(profiles)

    def resolve_profile_id(self, telemetry: dict[str, Any], preferred_profile: str | None = None) -> str:
        if preferred_profile and preferred_profile in self.profiles:
            return preferred_profile
        aircraft = str(telemetry.get("aircraft", {}).get("type", "")).lower()
        for profile in self.profiles.values():
            if aircraft and aircraft in profile.aircraft:
                return profile.id
        return "generic"

    def normalise_telemetry(self, telemetry: dict[str, Any], preferred_profile: str | None = None) -> dict[str, Any]:
        profile_id = self.resolve_profile_id(telemetry, preferred_profile)
        profile = self.profiles.get(profile_id) or self.profiles.get("generic")
        if profile is None:
            return telemetry

        normalised = dict(telemetry)
        tactical = dict(normalised.get("tactical", {}))
        alerts = tactical.get("rwr_alerts", [])
        if not isinstance(alerts, list):
            tactical["rwr_alerts"] = []
            normalised["tactical"] = tactical
            return normalised

        enriched = [self.normalise_alert(alert, profile) for alert in alerts if isinstance(alert, dict)]
        tactical["rwr_alerts"] = enriched
        tactical["rwr_profile"] = profile.id
        tactical["rwr_summary"] = self.summarise_alerts(enriched)
        normalised["tactical"] = tactical
        return normalised

    def normalise_alert(self, alert: dict[str, Any], profile: RwrAdapterProfile) -> dict[str, Any]:
        symbol = str(alert.get("symbol", alert.get("threat_type", ""))).upper()
        mapping = profile.mappings.get(symbol)
        if mapping is None:
            mapping = self.profiles.get("generic", profile).mappings.get(symbol) if "generic" in self.profiles else None

        enriched = dict(alert)
        enriched["symbol"] = symbol or str(alert.get("threat_type", "unknown")).upper()
        if mapping:
            enriched.setdefault("label", mapping.label)
            enriched.setdefault("threat_type", mapping.threat_type)
            enriched["severity"] = _max_severity(str(enriched.get("severity", mapping.severity)).lower(), mapping.severity)
        else:
            enriched.setdefault("label", enriched["symbol"] or "Unknown")
            enriched.setdefault("threat_type", str(alert.get("threat_type", "unknown")))
            enriched.setdefault("severity", str(alert.get("severity", "unknown")).lower())
        return enriched

    def summarise_alerts(self, alerts: list[dict[str, Any]]) -> str:
        if not alerts:
            return "No RWR threats"
        sorted_alerts = sorted(alerts, key=lambda item: DEFAULT_SEVERITY_ORDER.get(str(item.get("severity", "unknown")).lower(), 0), reverse=True)
        top = sorted_alerts[0]
        direction = top.get("direction", "unknown")
        label = top.get("label", top.get("threat_type", "unknown"))
        severity = top.get("severity", "unknown")
        return f"{severity} {label} {direction}"


def _max_severity(current: str, mapped: str) -> str:
    current_score = DEFAULT_SEVERITY_ORDER.get(current, 0)
    mapped_score = DEFAULT_SEVERITY_ORDER.get(mapped, 0)
    return current if current_score >= mapped_score else mapped


def normalise_rwr_telemetry(
    telemetry: dict[str, Any],
    profile_id: str | None = None,
    registry_path: str | Path = "config/rwr/adapters.json",
) -> dict[str, Any]:
    return RwrAdapterRegistry.from_json(registry_path).normalise_telemetry(telemetry, profile_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalise a telemetry JSON packet through an aircraft RWR adapter.")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--registry", default="config/rwr/adapters.json")
    parser.add_argument("--json", required=True, help="Path to a telemetry JSON file")
    args = parser.parse_args(argv)

    telemetry = json.loads(Path(args.json).read_text(encoding="utf-8"))
    normalised = normalise_rwr_telemetry(telemetry, args.profile, args.registry)
    print(json.dumps(normalised, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
