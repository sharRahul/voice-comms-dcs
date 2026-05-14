from __future__ import annotations

from voice_comms_dcs.config import Action, VoiceCommand
from voice_comms_dcs.matcher import CommandMatcher, find_best_match


def _commands() -> tuple[VoiceCommand, ...]:
    return (
        VoiceCommand("request_tanker", ("request tanker", "send tanker"), Action("flag", flag=1, value=1)),
        VoiceCommand("gear_down", ("gear down",), Action("flag", flag=2, value=1)),
    )


def test_exact_match():
    match = CommandMatcher.from_commands(_commands()).find_best_match("request tanker", 0.78)
    assert match is not None
    assert match.command.id == "request_tanker"
    assert match.confidence == 1.0


def test_substring_match():
    match = find_best_match("please request tanker now", _commands(), 0.78)
    assert match is not None
    assert match.command.id == "request_tanker"


def test_fuzzy_match():
    match = find_best_match("request tankr", _commands(), 0.78)
    assert match is not None
    assert match.command.id == "request_tanker"


def test_no_match_below_threshold():
    assert find_best_match("open canopy", _commands(), 0.9) is None


def test_exact_match_does_not_call_sequence_matcher(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("SequenceMatcher should not be used for exact matches")

    monkeypatch.setattr("voice_comms_dcs.matcher.SequenceMatcher", fail)
    match = CommandMatcher.from_commands(_commands()).find_best_match("gear down", 0.78)
    assert match is not None
    assert match.command.id == "gear_down"
