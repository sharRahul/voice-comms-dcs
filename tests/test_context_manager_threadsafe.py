from __future__ import annotations

from voice_comms_dcs.context_manager import AiMode, ContextManager


def test_get_context_returns_defensive_copy():
    manager = ContextManager()
    manager.update_telemetry({"internal": {"fuel_total_kg": 1200}})
    snapshot = manager.get_context()
    snapshot.telemetry["internal"]["fuel_total_kg"] = 1
    assert manager.get_context().telemetry["internal"]["fuel_total_kg"] == 1200


def test_add_turn_remains_bounded():
    manager = ContextManager(max_turns=2)
    manager.add_turn("pilot", "one")
    manager.add_turn("assistant", "two")
    manager.add_turn("pilot", "three")
    messages = manager.build_llm_messages("four")
    contents = [item["content"] for item in messages]
    assert "one" not in contents
    assert "two" in contents
    assert "three" in contents
    assert contents[-1] == "four"


def test_build_llm_messages_uses_consistent_snapshot():
    manager = ContextManager(aircraft_profile="test aircraft")
    manager.update_telemetry({"internal": {"g_load": 5.0}})
    messages = manager.build_llm_messages("status")
    assert manager.get_context().mode is AiMode.COMBAT
    assert messages[0]["role"] == "system"
    assert "test aircraft" in messages[0]["content"]
