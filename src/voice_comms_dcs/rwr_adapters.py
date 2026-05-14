from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


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


def _generic_profile() -> RwrAdapterProfile:
    return RwrAdapterProfile(
        id="generic",
        label="Generic RWR",
        aircraft=(),
        mappings={
            "SAM": RwrThreatMapping("SAM", "Surface-to-air threat", "sam", "spike"),
            "AAA": RwrThreatMapping("AAA", "Anti-air artillery", "aaa", "track"),
            "MSL": RwrThreatMapping("MSL", "Missile launch", "missile", "launch"),
            "M": RwrThreatMapping("M", "Missile launch", "missile", "missile"),
        },
    )


def default_registry() -> "RwrAdapterRegistry":
    return RwrAdapterRegistry({"generic": _generic_profile()})


def _ensure_generic_fallback(
    profiles: dict[str, RwrAdapterProfile],
) -> dict[str, RwrAdapterProfile]:
    fallback = _generic_profile()
    if "generic" not in profiles:
        profiles["generic"] = fallback
        return profiles

    generic = profiles["generic"]
    mappings = dict(fallback.mappings)
    mappings.update(generic.mappings)
    profiles["generic"] = RwrAdapterProfile(
        id=generic.id or "generic",
        label=generic.label or fallback.label,
        aircraft=generic.aircraft,
        mappings=mappings,
    )
    return profiles


class RwrAdapterRegistry:
    """Normalises aircraft-specific RWR symbols into Nimbus threat fields."""

    def __init__(self, profiles: dict[str, RwrAdapterProfile]) -> None:
        self.profiles = _ensure_generic_fallback(dict(profiles))

    @classmethod
    def from_json(cls, path: str | Path = "config/rwr/adapters.json") -> "RwrAdapterRegistry":
        file_path = Path(path)
        if not file_path.exists():
            logger.warning("RWR adapter registry missing at %s; using generic fallback.", path)
            return default_registry()

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("RWR adapter registry %s is unreadable; using generic fallback: %s", file_path, exc)
            return default_registry()

        profiles: dict[str, RwrAdapterProfile] = {}
        raw_profiles = data.get("profiles", []) if isinstance(data, dict) else []
        if not isinstance(raw_profiles, list):
            logger.warning("RWR adapter registry %s has invalid profiles; using generic fallback.", file_path)
            return default_registry()

        for raw in raw_profiles:
            if not isinstance(raw, dict):
                logger.warning("Skipping invalid RWR profile entry in %s.", file_path)
                continue
            profile_id = str(raw.get("id", "")).strip()
            if not profile_id:
                logger.warning("Skipping RWR profile without an id in %s.", file_path)
                continue

            mappings: dict[str, RwrThreatMapping] = {}
            raw_mappings = raw.get("mappings", {})
            if isinstance(raw_mappings, dict):
                for symbol, mapping in raw_mappings.items():
                    if not isinstance(mapping, dict):
                        logger.warning("Skipping invalid RWR mapping %s in profile %s.", symbol, profile_id)
                        continue
                    normalised_symbol = str(symbol).upper()
                    mappings[normalised_symbol] = RwrThreatMapping(
                        symbol=normalised_symbol,
                        label=str(mapping.get("label", symbol)),
                        threat_type=str(mapping.get("threat_type", "unknown")),
                        severity=str(mapping.get("severity", "search")).lower(),
                    )

            raw_aircraft = raw.get("aircraft", [])
            aircraft = (
                tuple(str(item).lower() for item in raw_aircraft)
                if isinstance(raw_aircraft, list)
                else ()
            )
            profiles[profile_id] = RwrAdapterProfile(
                id=profile_id,
                label=str(raw.get("label", profile_id)),
                aircraft=aircraft,
                mappings=mappings,
            )

        if not profiles:
            logger.warning("RWR adapter registry %s had no valid profiles; using generic fallback.", file_path)
            return default_registry()
        return cls(profiles)

    def resolve_profile_id(self, telemetry: dict[str, Any], preferred_profile: str | None = None) -> str:
        if preferred_profile and preferred_profile in self.profiles:
            return preferred_profile
        aircraft_payload = telemetry.get("aircraft", {}) if isinstance(telemetry, dict) else {}
        aircraft = str(aircraft_payload.get("type", "") if isinstance(aircraft_payload, dict) else "").lower()
        for profile in self.profiles.values():
            if aircraft and aircraft in profile.aircraft:
                return profile.id
        return "generic"

    def normalise_telemetry(self, telemetry: dict[str, Any], preferred_profile: str | None = None) -> dict[str, Any]:
        if not isinstance(telemetry, dict):
            return {"tactical": {"rwr_alerts": [], "rwr_profile": "generic", "rwr_summary": "No RWR threats"}}

        profile_id = self.resolve_profile_id(telemetry, preferred_profile)
        profile = self.profiles.get(profile_id) or self.profiles.get("generic")
        if profile is None:
            return telemetry

        normalised = dict(telemetry)
        tactical_raw = normalised.get("tactical", {})
        tactical = dict(tactical_raw) if isinstance(tactical_raw, dict) else {}
        alerts = tactical.get("rwr_alerts", [])
        if not isinstance(alerts, list):
            tactical["rwr_alerts"] = []
            tactical["rwr_profile"] = profile.id
            tactical["rwr_summary"] = "No RWR threats"
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
            generic = self.profiles.get("generic", profile)
            mapping = generic.mappings.get(symbol)

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
