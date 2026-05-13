from __future__ import annotations

import argparse
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
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


PttCallback = Callable[[PttEvent], None]


class InputManager:
    """Global keyboard + non-exclusive joystick PTT manager.

    pygame joystick polling reads device state without taking exclusive control of the HOTAS, so it
    should not interfere with DCS native input. pynput keyboard capture is global on Windows and does
    not require the Python window to have focus.
    """

    def __init__(self, config: InputManagerConfig | None = None) -> None:
        self.config = config or InputManagerConfig()
        self.events: queue.Queue[PttEvent] = queue.Queue()
        self._callbacks: list[PttCallback] = []
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._keyboard_listener: Any | None = None
        self._ptt_active = False
        self._lock = threading.Lock()

    @property
    def ptt_active(self) -> bool:
        with self._lock:
            return self._ptt_active

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
            self._keyboard_listener.stop()
            self._keyboard_listener = None
        for thread in self._threads:
            thread.join(timeout=1.0)
        self._threads.clear()
        if pygame is not None:
            try:
                pygame.joystick.quit()
                pygame.quit()
            except Exception:
                pass

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
                continue

    def _joystick_loop(self) -> None:
        if pygame is None:
            return
        try:
            pygame.init()
            pygame.joystick.init()
        except Exception:
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
                if joystick is None:
                    time.sleep(1.0)
                    continue

                pygame.event.pump()
                if joystick.get_numbuttons() <= binding.button_index:
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
                time.sleep(0.5)
            time.sleep(poll_delay)

    def _start_keyboard_listener(self) -> None:
        if keyboard is None:
            return
        target_key = _parse_key(self.config.keyboard.hotkey)

        def on_press(key: Any) -> None:
            if _key_matches(key, target_key):
                self._publish(PttEventType.START_PTT, "keyboard", self.config.keyboard.hotkey)

        def on_release(key: Any) -> None:
            if _key_matches(key, target_key):
                self._publish(PttEventType.STOP_PTT, "keyboard", self.config.keyboard.hotkey)

        self._keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._keyboard_listener.start()


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
        return []
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
