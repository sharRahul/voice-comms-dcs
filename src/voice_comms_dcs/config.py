from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when commands.json is missing required fields."""


@dataclass(frozen=True)
class Action:
    type: str
    flag: int | None = None
    value: int | None = None
    command: str | None = None


@dataclass(frozen=True)
class VoiceCommand:
    id: str
    phrases: tuple[str, ...]
    action: Action
    description: str = ""


@dataclass(frozen=True)
class SttConfig:
    engine: str = "vosk"
    model_path: str = "models/vosk-model-small-en-us-0.15"
    sample_rate: int = 16000
    device: str | int | None = None


@dataclass(frozen=True)
class AppConfig:
    dcs_host: str
    dcs_port: int
    min_confidence: float
    stt: SttConfig
    commands: tuple[VoiceCommand, ...]


def _normalise_phrase(phrase: str) -> str:
    return " ".join(phrase.lower().strip().split())


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    data = json.loads(config_path.read_text(encoding="utf-8"))

    commands: list[VoiceCommand] = []
    seen_ids: set[str] = set()
    for raw in data.get("commands", []):
        command_id = str(raw.get("id", "")).strip()
        if not command_id:
            raise ConfigError("Every command must have a non-empty id.")
        if command_id in seen_ids:
            raise ConfigError(f"Duplicate command id: {command_id}")
        seen_ids.add(command_id)

        phrases = tuple(
            phrase
            for phrase in (_normalise_phrase(p) for p in raw.get("phrases", []))
            if phrase
        )
        if not phrases:
            raise ConfigError(f"Command {command_id!r} must define at least one phrase.")

        raw_action: dict[str, Any] = raw.get("action", {})
        action_type = str(raw_action.get("type", "")).strip().lower()
        if action_type == "flag":
            action = Action(
                type="flag",
                flag=int(raw_action["flag"]),
                value=int(raw_action.get("value", 1)),
            )
        elif action_type == "command":
            action = Action(type="command", command=str(raw_action["command"]))
        else:
            raise ConfigError(
                f"Command {command_id!r} has unsupported action type {action_type!r}. "
                "Supported types: flag, command."
            )

        commands.append(
            VoiceCommand(
                id=command_id,
                description=str(raw.get("description", "")),
                phrases=phrases,
                action=action,
            )
        )

    if not commands:
        raise ConfigError("At least one command must be configured.")

    stt_data = data.get("stt", {})
    matching_data = data.get("matching", {})

    return AppConfig(
        dcs_host=str(data.get("dcs_host", "127.0.0.1")),
        dcs_port=int(data.get("dcs_port", 10308)),
        min_confidence=float(matching_data.get("min_confidence", 0.78)),
        stt=SttConfig(
            engine=str(stt_data.get("engine", "vosk")).lower(),
            model_path=str(stt_data.get("model_path", "models/vosk-model-small-en-us-0.15")),
            sample_rate=int(stt_data.get("sample_rate", 16000)),
            device=stt_data.get("device"),
        ),
        commands=tuple(commands),
    )
