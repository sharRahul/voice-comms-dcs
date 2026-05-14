from __future__ import annotations

from pathlib import Path

from voice_comms_dcs.rwr_adapters import RwrAdapterRegistry


def test_missing_registry_returns_generic_fallback(tmp_path):
    registry = RwrAdapterRegistry.from_json(tmp_path / "missing.json")

    assert "generic" in registry.profiles
    assert "SAM" in registry.profiles["generic"].mappings


def test_invalid_json_returns_generic_fallback(tmp_path):
    path = tmp_path / "adapters.json"
    path.write_text("not json", encoding="utf-8")

    registry = RwrAdapterRegistry.from_json(path)

    assert "generic" in registry.profiles


def test_empty_profiles_returns_generic_fallback(tmp_path):
    path = tmp_path / "adapters.json"
    path.write_text('{"profiles": []}', encoding="utf-8")

    registry = RwrAdapterRegistry.from_json(path)

    assert "generic" in registry.profiles


def test_valid_profile_loads_and_keeps_generic_fallback(tmp_path):
    path = tmp_path / "adapters.json"
    path.write_text(
        '{"profiles": [{"id": "test", "label": "Test", "aircraft": ["x"], "mappings": {"T": {"label": "Threat", "threat_type": "sam", "severity": "spike"}}}]}',
        encoding="utf-8",
    )

    registry = RwrAdapterRegistry.from_json(path)

    assert "test" in registry.profiles
    assert "generic" in registry.profiles


def test_normalise_telemetry_handles_malformed_rwr_alerts(tmp_path):
    registry = RwrAdapterRegistry.from_json(tmp_path / "missing.json")

    telemetry = registry.normalise_telemetry({"tactical": {"rwr_alerts": "bad"}})

    assert telemetry["tactical"]["rwr_alerts"] == []
    assert telemetry["tactical"]["rwr_profile"] == "generic"
    assert telemetry["tactical"]["rwr_summary"] == "No RWR threats"
