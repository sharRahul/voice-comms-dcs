from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .input_manager import InputManagerConfig, JoystickButtonBinding, KeyboardBinding


@dataclass(frozen=True)
class JoystickPreset:
    id: str
    label: str
    device_hint: str
    joystick_index: int
    button_index: int
    hotkey: str
    notes: str = ""

    def to_input_config(self, *, joystick_enabled: bool = True, keyboard_enabled: bool = True) -> InputManagerConfig:
        return InputManagerConfig(
            joystick_enabled=joystick_enabled,
            keyboard_enabled=keyboard_enabled,
            joystick=JoystickButtonBinding(self.joystick_index, self.button_index),
            keyboard=KeyboardBinding(self.hotkey),
        )


def load_joystick_presets(path: str | Path = "config/joystick_profiles/presets.json") -> dict[str, JoystickPreset]:
    file_path = Path(path)
    if not file_path.exists():
        file_path = Path(__file__).resolve().parents[2] / "config" / "joystick_profiles" / "presets.json"
    data = json.loads(file_path.read_text(encoding="utf-8"))
    presets: dict[str, JoystickPreset] = {}
    for item in data.get("presets", []):
        preset = JoystickPreset(
            id=str(item["id"]),
            label=str(item["label"]),
            device_hint=str(item.get("device_hint", "")),
            joystick_index=int(item.get("joystick_index", 0)),
            button_index=int(item.get("button_index", 1)),
            hotkey=str(item.get("hotkey", "right_ctrl")),
            notes=str(item.get("notes", "")),
        )
        presets[preset.id] = preset
    return presets


def resolve_joystick_preset(profile_id: str | None, path: str | Path = "config/joystick_profiles/presets.json") -> JoystickPreset | None:
    if not profile_id:
        return None
    return load_joystick_presets(path).get(profile_id)


def presets_as_api_payload(path: str | Path = "config/joystick_profiles/presets.json") -> dict[str, Any]:
    presets = load_joystick_presets(path)
    return {
        "presets": [
            {
                "id": preset.id,
                "label": preset.label,
                "device_hint": preset.device_hint,
                "joystick_index": preset.joystick_index,
                "button_index": preset.button_index,
                "hotkey": preset.hotkey,
                "notes": preset.notes,
            }
            for preset in presets.values()
        ]
    }
