from __future__ import annotations

import logging

from voice_comms_dcs import input_manager as input_module
from voice_comms_dcs.input_manager import InputManager, PttEventType


def test_callback_exception_is_recorded_and_logged(caplog):
    manager = InputManager()

    def failing_callback(_event):
        raise RuntimeError("boom")

    manager.subscribe(failing_callback)

    with caplog.at_level(logging.ERROR, logger="voice_comms_dcs.input_manager"):
        manager._publish(PttEventType.START_PTT, "test")

    diagnostics = manager.diagnostics()
    assert diagnostics.last_error_code == "callback_error"
    assert diagnostics.last_error == "PTT callback raised unexpectedly."
    assert any("callback_error" in record.message for record in caplog.records)


def test_repeated_errors_are_rate_limited(caplog):
    manager = InputManager()

    with caplog.at_level(logging.WARNING, logger="voice_comms_dcs.input_manager"):
        manager._record_error("same_error", "first")
        manager._record_error("same_error", "second")

    messages = [record.message for record in caplog.records if "same_error" in record.message]
    assert len(messages) == 1
    diagnostics = manager.diagnostics()
    assert diagnostics.last_error_code == "same_error"
    assert diagnostics.last_error == "second"


def test_missing_optional_input_dependencies_record_safe_diagnostics(monkeypatch):
    monkeypatch.setattr(input_module, "pygame", None)
    monkeypatch.setattr(input_module, "keyboard", None)
    manager = InputManager()

    manager._joystick_loop()
    manager._start_keyboard_listener()

    diagnostics = manager.diagnostics()
    assert diagnostics.joystick_available is False
    assert diagnostics.keyboard_available is False
    assert diagnostics.last_error_code in {"joystick_pygame_unavailable", "keyboard_unavailable"}
