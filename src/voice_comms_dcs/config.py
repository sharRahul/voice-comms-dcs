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
class LanguageConfig:
    selected: str = "en"
    installed: tuple[str, ...] = ("en",)


@dataclass(frozen=True)
class SttConfig:
    engine: str = "whisper_cpp"
    model_path: str = "models/whisper/ggml-base.en.bin"
    sample_rate: int = 16000
    device: str | int | None = None
    language: str = "en"


@dataclass(frozen=True)
class LlmConfig:
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:0.5b"
    recommended_model: str = "qwen2.5:1.5b"
    high_quality_model: str = "llama3.2:3b"
    timeout_seconds: float = 3.0


@dataclass(frozen=True)
class TtsConfig:
    engine: str = "piper"
    piper_exe: str = "piper"
    piper_model: str = "models/piper/en_US-lessac-low.onnx"
    optional_male_model: str = "models/piper/en_US-ryan-low.onnx"
    language: str = "en"
    bandpass_low_hz: float = 300.0
    bandpass_high_hz: float = 3000.0
    static_level: float = 0.012


@dataclass(frozen=True)
class AppConfig:
    dcs_host: str
    dcs_port: int
    min_confidence: float
    language: LanguageConfig
    stt: SttConfig
    llm: LlmConfig
    tts: TtsConfig
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

    language_data = data.get("language", {}) if isinstance(data.get("language", {}), dict) else {}
    selected_language = str(language_data.get("selected", data.get("selected_language", "en"))).lower()
    installed_languages = tuple(
        str(language).lower() for language in language_data.get("installed", [selected_language])
    )

    stt_data = data.get("stt", {})
    llm_data = data.get("llm", {})
    tts_data = data.get("tts", {})
    radio_filter = tts_data.get("radio_filter", {}) if isinstance(tts_data.get("radio_filter", {}), dict) else {}
    matching_data = data.get("matching", {})

    return AppConfig(
        dcs_host=str(data.get("dcs_host", "127.0.0.1")),
        dcs_port=int(data.get("dcs_port", 10308)),
        min_confidence=float(matching_data.get("min_confidence", 0.78)),
        language=LanguageConfig(
            selected=selected_language,
            installed=installed_languages or (selected_language,),
        ),
        stt=SttConfig(
            engine=str(stt_data.get("engine", "whisper_cpp")).lower(),
            model_path=str(stt_data.get("model_path", "models/whisper/ggml-base.en.bin")),
            sample_rate=int(stt_data.get("sample_rate", 16000)),
            device=stt_data.get("device"),
            language=str(stt_data.get("language", selected_language)).lower(),
        ),
        llm=LlmConfig(
            provider=str(llm_data.get("provider", "ollama")).lower(),
            base_url=str(llm_data.get("base_url", "http://127.0.0.1:11434")),
            model=str(llm_data.get("model", "qwen2.5:0.5b")),
            recommended_model=str(llm_data.get("recommended_model", "qwen2.5:1.5b")),
            high_quality_model=str(llm_data.get("high_quality_model", "llama3.2:3b")),
            timeout_seconds=float(llm_data.get("timeout_seconds", 3.0)),
        ),
        tts=TtsConfig(
            engine=str(tts_data.get("engine", "piper")).lower(),
            piper_exe=str(tts_data.get("piper_exe", "piper")),
            piper_model=str(tts_data.get("piper_model", "models/piper/en_US-lessac-low.onnx")),
            optional_male_model=str(tts_data.get("optional_male_model", "models/piper/en_US-ryan-low.onnx")),
            language=str(tts_data.get("language", selected_language)).lower(),
            bandpass_low_hz=float(radio_filter.get("bandpass_low_hz", 300.0)),
            bandpass_high_hz=float(radio_filter.get("bandpass_high_hz", 3000.0)),
            static_level=float(radio_filter.get("static_level", 0.012)),
        ),
        commands=tuple(commands),
    )
