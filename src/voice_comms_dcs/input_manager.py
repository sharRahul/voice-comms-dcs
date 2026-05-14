from __future__ import annotations

import argparse
import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

try:
    import pygame
except Exception:  # pragma: no cover - optional runtime dependency diagnostics
    pygame = None  # type: ignore[assignment]

try:
    from pynput import keyboard
except Exception:  # pragma: no cover - optional runtime dependency diagnostics
    keyboard = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class PttEventType(str, Enum):
    START_PTT = "START_PTT"
    STOP_PTT = "STOP_PTT"


@dataclass(frozen=True)
class PttEvent:
    type: PttEventType
    source: str
    timestamp: float
    detail: str = ""


@dataclass(frozen=True)
class JoystickButtonBinding:
    joystick_index: int = 0
    button_index: int = 1


@dataclass(frozen=True)
class KeyboardBinding:
    hotkey: str = "right_ctrl"


@dataclass(frozen=True)
class InputManagerConfig:
    joystick_enabled: bool = True
    keyboard_enabled: bool = True
    joystick: JoystickButtonBinding = JoystickButtonBinding()
    keyboard: KeyboardBinding = KeyboardBinding()
    poll_hz: float = 60.0


@dataclass(frozen=True)
class InputDiagnostics:
    joystick_available: bool = False
    keyboard_available: bool = False
    last_error: str = ""
    last_error_code: str = ""
    last_error_at: float = 0.0
    joystick_name: str = ""
    joystick_button_count: int = 0


PttCallback = Callable[[PttEvent], None]


class InputManager:
    """Global keyboard + non-exclusive joystick PTT manager.

    pygame joystick polling reads device state without taking exclusive control of the HOTAS, so it
    should not interfere with DCS native input. pynput keyboard capture is global on Windows and does
    not require the Python window to have focus.
    """

    _ERROR_LOG_INTERVAL_SECONDS = 10.0

    def __init__(self, config: InputManagerConfig | None = None) -> None:
        self.config = config or InputManagerConfig()
        self.events: queue.Queue[PttEvent] = queue.Queue()
        self._callbacks: list[PttCallback] = []
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._keyboard_listener: Any | None = None
        self._ptt_active = False
        self._lock = threading.Lock()
        self._diagnostics = InputDiagnostics()
        self._last_error_logs: dict[str, float] = {}

    @property
    def ptt_active(self) -> bool:
        with self._lock:
            return self._ptt_active

    def diagnostics(self) -> InputDiagnostics:
        with self._lock:
            return self._diagnostics

    def subscribe(self, callback: PttCallback) -> None:
        self._callbacks.append(callback)

    def start(self) -> None:
        self._stop.clear()
        if self.config.joystick_enabled:
            thread = threading.Thread(target=self._joystick_loop, name="vcdcs-joystick-ptt", daemon=True)
            thread.start()
            self._threads.append(thread)
        if self.config.keyboard_enabled:
            self._start_keyboard_listener()

    def stop(self) -> None:
        self._stop.set()
        if self._keyboard_listener is not None:
            try:
                self._keyboard_listener.stop()
            except Exception:
                self._record_error(
                    "keyboard_stop_failed",
                    "Keyboard listener failed to stop cleanly.",
                    exc_info=True,
                    level=logging.WARNING,
                )
            self._keyboard_listener = None
        for thread in self._threads:
            thread.join(timeout=1.0)
        self._threads.clear()
        if pygame is not None:
            try:
                pygame.joystick.quit()
                pygame.quit()
            except Exception:
                self._record_error(
                    "pygame_shutdown_failed",
                    "Pygame joystick subsystem failed to stop cleanly.",
                    exc_info=True,
                    level=logging.DEBUG,
                )

    def _update_diagnostics(self, **changes: Any) -> None:
        with self._lock:
            self._diagnostics = replace(self._diagnostics, **changes)

    def _record_error(
        self,
        code: str,
        message: str,
        *,
        exc_info: bool = False,
        level: int = logging.WARNING,
    ) -> None:
        now = time.monotonic()
        should_log = False
        with self._lock:
            last_logged = self._last_error_logs.get(code, 0.0)
            if now - last_logged >= self._ERROR_LOG_INTERVAL_SECONDS:
                self._last_error_logs[code] = now
                should_log = True
            self._diagnostics = replace(
                self._diagnostics,
                last_error=message,
                last_error_code=code,
                last_error_at=now,
            )
        if should_log:
            logger.log(level, "%s: %s", code, message, exc_info=exc_info)

    def _publish(self, event_type: PttEventType, source: str, detail: str = "") -> None:
        with self._lock:
            if event_type is PttEventType.START_PTT and self._ptt_active:
                return
            if event_type is PttEventType.STOP_PTT and not self._ptt_active:
                return
            self._ptt_active = event_type is PttEventType.START_PTT

        event = PttEvent(type=event_type, source=source, timestamp=time.monotonic(), detail=detail)
        self.events.put(event)
        for callback in list(self._callbacks):
            try:
                callback(event)
            except Exception:
                self._record_error(
                    "callback_error",
                    "PTT callback raised unexpectedly.",
                    exc_info=True,
                    level=logging.ERROR,
                )

    def _joystick_loop(self) -> None:
        if pygame is None:
            self._record_error(
                "joystick_pygame_unavailable",
                "Joystick support is unavailable because pygame could not be imported.",
                level=logging.WARNING,
            )
            self._update_diagnostics(joystick_available=False)
            return
        try:
            pygame.init()
            pygame.joystick.init()
        except Exception:
            self._record_error(
                "joystick_init_failed",
                "Joystick subsystem failed to initialise.",
                exc_info=True,
                level=logging.WARNING,
            )
            self._update_diagnostics(joystick_available=False)
            return

        binding = self.config.joystick
        joystick: Any | None = None
        last_state = False
        poll_delay = 1.0 / max(self.config.poll_hz, 1.0)

        while not self._stop.is_set():
            try:
                count = pygame.joystick.get_count()
                if joystick is None and count > binding.joystick_index:
                    joystick = pygame.joystick.Joystick(binding.joystick_index)
                    joystick.init()
                    self._update_diagnostics(
                        joystick_available=True,
                        joystick_name=str(joystick.get_name()),
                        joystick_button_count=int(joystick.get_numbuttons()),
                    )
                    logger.info(
                        "Joystick PTT device ready: index=%s name=%s buttons=%s",
                        binding.joystick_index,
                        joystick.get_name(),
                        joystick.get_numbuttons(),
                    )
                if joystick is None:
                    self._update_diagnostics(joystick_available=False)
                    self._record_error(
                        "joystick_not_found",
                        "Configured joystick was not found.",
                        level=logging.DEBUG,
                    )
                    time.sleep(1.0)
                    continue

                pygame.event.pump()
                button_count = joystick.get_numbuttons()
                if button_count <= binding.button_index:
                    self._update_diagnostics(joystick_button_count=int(button_count))
                    self._record_error(
                        "joystick_button_missing",
                        "Configured joystick button does not exist on the selected device.",
                        level=logging.DEBUG,
                    )
                    time.sleep(poll_delay)
                    continue

                state = bool(joystick.get_button(binding.button_index))
                if state and not last_state:
                    self._publish(
                        PttEventType.START_PTT,
                        "joystick",
                        f"joystick={binding.joystick_index} button={binding.button_index}",
                    )
                elif not state and last_state:
                    self._publish(
                        PttEventType.STOP_PTT,
                        "joystick",
                        f"joystick={binding.joystick_index} button={binding.button_index}",
                    )
                last_state = state
            except Exception:
                self._record_error(
                    "joystick_poll_failed",
                    "Joystick polling failed.",
                    exc_info=True,
                    level=logging.DEBUG,
                )
                time.sleep(0.5)
            time.sleep(poll_delay)

    def _start_keyboard_listener(self) -> None:
        if keyboard is None:
            self._record_error(
                "keyboard_unavailable",
                "Keyboard support is unavailable because pynput could not be imported.",
                level=logging.WARNING,
            )
            self._update_diagnostics(keyboard_available=False)
            return
        target_key = _parse_key(self.config.keyboard.hotkey)

        def on_press(key: Any) -> None:
            if _key_matches(key, target_key):
                self._publish(PttEventType.START_PTT, "keyboard", self.config.keyboard.hotkey)

        def on_release(key: Any) -> None:
            if _key_matches(key, target_key):
                self._publish(PttEventType.STOP_PTT, "keyboard", self.config.keyboard.hotkey)

        try:
            self._keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._keyboard_listener.start()
            self._update_diagnostics(keyboard_available=True)
        except Exception:
            self._record_error(
                "keyboard_listener_failed",
                "Keyboard listener failed to start.",
                exc_info=True,
                level=logging.WARNING,
            )
            self._update_diagnostics(keyboard_available=False)


def _parse_key(name: str) -> Any:
    normalised = name.lower().strip().replace("-", "_").replace(" ", "_")
    aliases = {
        "right_ctrl": "ctrl_r",
        "left_ctrl": "ctrl_l",
        "right_alt": "alt_r",
        "left_alt": "alt_l",
        "spacebar": "space",
    }
    normalised = aliases.get(normalised, normalised)
    if keyboard is not None and hasattr(keyboard.Key, normalised):
        return getattr(keyboard.Key, normalised)
    return normalised


def _key_matches(key: Any, target: Any) -> bool:
    if key == target:
        return True
    char = getattr(key, "char", None)
    if isinstance(target, str) and char:
        return char.lower() == target.lower()
    return False


def list_joysticks() -> list[dict[str, Any]]:
    if pygame is None:
        logger.warning("Joystick listing requested but pygame is unavailable.")
        return []
    try:
        pygame.init()
        pygame.joystick.init()
        devices: list[dict[str, Any]] = []
        for index in range(pygame.joystick.get_count()):
            js = pygame.joystick.Joystick(index)
            js.init()
            devices.append(
                {
                    "index": index,
                    "name": js.get_name(),
                    "buttons": js.get_numbuttons(),
                    "axes": js.get_numaxes(),
                    "hats": js.get_numhats(),
                }
            )
        return devices
    except Exception:
        logger.exception("Failed to list joystick devices.")
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect joystick devices and test global PTT events.")
    parser.add_argument("--list", action="store_true", help="List available joystick/HOTAS devices.")
    parser.add_argument("--joystick-index", type=int, default=0)
    parser.add_argument("--button-index", type=int, default=1)
    parser.add_argument("--hotkey", default="right_ctrl")
    args = parser.parse_args(argv)

    if args.list:
        for device in list_joysticks():
            print(device)
        return 0

    manager = InputManager(
        InputManagerConfig(
            joystick=JoystickButtonBinding(args.joystick_index, args.button_index),
            keyboard=KeyboardBinding(args.hotkey),
        )
    )
    manager.subscribe(lambda event: print(event))
    manager.start()
    print("Listening for PTT. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        manager.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
