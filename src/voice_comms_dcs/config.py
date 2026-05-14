from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_config import ensure_default_config


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
class TelemetryConfig:
    host: str = "127.0.0.1"
    port: int = 10309
    max_age_seconds: float = 2.0


@dataclass(frozen=True)
class WebRtcConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    dashboard_path: str = "/dashboard"
    vad_rms_threshold: float = 0.012
    vad_hangover_frames: int = 8


@dataclass(frozen=True)
class InputConfig:
    keyboard_enabled: bool = True
    joystick_enabled: bool = True
    hotkey: str = "right_ctrl"
    joystick_index: int = 0
    joystick_button: int = 1
    poll_hz: float = 60.0


@dataclass(frozen=True)
class PushToTalkConfig:
    enabled: bool = True
    hotkey: str = "right_ctrl"
    release_grace_ms: int = 300
    pre_roll_ms: int = 500
    max_context_ms: int = 15000


@dataclass(frozen=True)
class UdpReliabilityConfig:
    enabled: bool = True
    require_ack: bool = False
    retries: int = 0
    ack_timeout_seconds: float = 0.05
    replay_window_size: int = 128
    protocol_version: int = 2


@dataclass(frozen=True)
class DashboardPrivacyConfig:
    expose_position: bool = False
    expose_tactical: bool = True
    expose_context: bool = True
    expose_model_paths: bool = False
    expose_last_transcript: bool = True


@dataclass(frozen=True)
class SttConfig:
    engine: str = "whisper_cpp"
    model_path: str = "models/whisper/ggml-base.en.bin"
    sample_rate: int = 16000
    device: str | int | None = None
    language: str = "en"
    whisper_engine: str = "auto"
    cli_exe: str = "whisper-cli"
    threads: int = 4
    beam_size: int = 1
    pre_roll_ms: int = 500
    max_context_ms: int = 15000
    highpass_hz: float = 120.0
    lowpass_hz: float = 7600.0
    cli_timeout_seconds: float = 30.0


@dataclass(frozen=True)
class LlmConfig:
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:0.5b"
    recommended_model: str = "qwen2.5:1.5b"
    high_quality_model: str = "llama3.2:3b"
    timeout_seconds: float = 8.0


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
    piper_timeout_seconds: float = 30.0


@dataclass(frozen=True)
class AppConfig:
    dcs_host: str
    dcs_port: int
    min_confidence: float
    language: LanguageConfig
    telemetry: TelemetryConfig
    webrtc: WebRtcConfig
    input: InputConfig
    push_to_talk: PushToTalkConfig
    udp_reliability: UdpReliabilityConfig
    dashboard_privacy: DashboardPrivacyConfig
    stt: SttConfig
    llm: LlmConfig
    tts: TtsConfig
    commands: tuple[VoiceCommand, ...]


@dataclass(frozen=True)
class BridgeRuntimeConfig:
    host: str
    port: int
    telemetry_host: str
    telemetry_port: int
    ptt_hotkey: str
    joystick_index: int
    joystick_button: int
    keyboard_enabled: bool
    joystick_enabled: bool
    poll_hz: float
    pre_roll_ms: int
    max_context_ms: int
    vad_rms_threshold: float
    vad_hangover_frames: int


def _normalise_phrase(phrase: str) -> str:
    return " ".join(phrase.lower().strip().split())


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _as_int(value: Any, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_str(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value)


def _as_str_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, list):
        return default
    items = tuple(str(item).lower() for item in value if str(item).strip())
    return items or default


def _required_int(raw: dict[str, Any], key: str, command_id: str) -> int:
    if key not in raw:
        raise ConfigError(f"Command {command_id!r} action must define {key!r}.")
    try:
        return int(raw[key])
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Command {command_id!r} action field {key!r} must be an integer.") from exc


def _load_commands(data: dict[str, Any]) -> tuple[VoiceCommand, ...]:
    commands: list[VoiceCommand] = []
    seen_ids: set[str] = set()
    for raw_value in data.get("commands", []):
        raw = _as_dict(raw_value)
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

        raw_action = _as_dict(raw.get("action", {}))
        action_type = str(raw_action.get("type", "")).strip().lower()
        if action_type == "flag":
            action = Action(
                type="flag",
                flag=_required_int(raw_action, "flag", command_id),
                value=int(_as_int(raw_action.get("value"), 1) or 1),
            )
        elif action_type == "command":
            command = str(raw_action.get("command", "")).strip()
            if not command:
                raise ConfigError(f"Command {command_id!r} action must define a non-empty command.")
            action = Action(type="command", command=command)
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
    return tuple(commands)


def _parse_udp_reliability(data: dict[str, Any]) -> UdpReliabilityConfig:
    raw = _as_dict(data.get("udp_reliability", data.get("network", {})))
    raw = _as_dict(raw.get("udp_reliability", raw))
    return UdpReliabilityConfig(
        enabled=_as_bool(raw.get("enabled"), True),
        require_ack=_as_bool(raw.get("require_ack"), False),
        retries=max(0, int(_as_int(raw.get("retries"), 0) or 0)),
        ack_timeout_seconds=max(0.001, _as_float(raw.get("ack_timeout_seconds"), 0.05)),
        replay_window_size=max(1, int(_as_int(raw.get("replay_window_size"), 128) or 128)),
        protocol_version=max(1, int(_as_int(raw.get("protocol_version"), 2) or 2)),
    )


def _parse_dashboard_privacy(data: dict[str, Any]) -> DashboardPrivacyConfig:
    dashboard_data = _as_dict(data.get("dashboard", {}))
    raw = _as_dict(dashboard_data.get("privacy", data.get("dashboard_privacy", {})))
    return DashboardPrivacyConfig(
        expose_position=_as_bool(raw.get("expose_position"), False),
        expose_tactical=_as_bool(raw.get("expose_tactical"), True),
        expose_context=_as_bool(raw.get("expose_context"), True),
        expose_model_paths=_as_bool(raw.get("expose_model_paths"), False),
        expose_last_transcript=_as_bool(raw.get("expose_last_transcript"), True),
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = ensure_default_config(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    data = json.loads(config_path.read_text(encoding="utf-8"))
    commands = _load_commands(data)

    language_data = _as_dict(data.get("language", {}))
    selected_language = _as_str(language_data.get("selected", data.get("selected_language", "en")), "en").lower()
    installed_languages = _as_str_tuple(language_data.get("installed"), (selected_language,))

    telemetry_data = _as_dict(data.get("telemetry", {}))
    webrtc_data = _as_dict(data.get("webrtc", {}))
    vad_data = _as_dict(webrtc_data.get("vad", {}))
    input_data = _as_dict(data.get("input", {}))
    ptt_data = _as_dict(data.get("push_to_talk", {}))
    stt_data = _as_dict(data.get("stt", {}))
    whisper_data = _as_dict(stt_data.get("whisper", {}))
    llm_data = _as_dict(data.get("llm", {}))
    tts_data = _as_dict(data.get("tts", {}))
    radio_filter = _as_dict(tts_data.get("radio_filter", {}))
    matching_data = _as_dict(data.get("matching", {}))

    ptt_hotkey = _as_str(ptt_data.get("hotkey", input_data.get("hotkey", "right_ctrl")), "right_ctrl")
    ptt_pre_roll = int(_as_int(ptt_data.get("pre_roll_ms", whisper_data.get("pre_roll_ms")), 500) or 500)
    ptt_max_context = int(_as_int(ptt_data.get("max_context_ms", whisper_data.get("max_context_ms")), 15000) or 15000)

    return AppConfig(
        dcs_host=_as_str(data.get("dcs_host"), "127.0.0.1"),
        dcs_port=int(_as_int(data.get("dcs_port"), 10308) or 10308),
        min_confidence=_as_float(matching_data.get("min_confidence"), 0.78),
        language=LanguageConfig(selected=selected_language, installed=installed_languages),
        telemetry=TelemetryConfig(
            host=_as_str(telemetry_data.get("host"), "127.0.0.1"),
            port=int(_as_int(telemetry_data.get("port"), 10309) or 10309),
            max_age_seconds=_as_float(telemetry_data.get("max_age_seconds"), 2.0),
        ),
        webrtc=WebRtcConfig(
            host=_as_str(webrtc_data.get("host"), "127.0.0.1"),
            port=int(_as_int(webrtc_data.get("port"), 8765) or 8765),
            dashboard_path=_as_str(webrtc_data.get("dashboard_path"), "/dashboard"),
            vad_rms_threshold=_as_float(vad_data.get("rms_threshold"), 0.012),
            vad_hangover_frames=int(_as_int(vad_data.get("hangover_frames"), 8) or 8),
        ),
        input=InputConfig(
            keyboard_enabled=_as_bool(input_data.get("keyboard_enabled"), True),
            joystick_enabled=_as_bool(input_data.get("joystick_enabled"), True),
            hotkey=_as_str(input_data.get("hotkey"), "right_ctrl"),
            joystick_index=int(_as_int(input_data.get("joystick_index"), 0) or 0),
            joystick_button=int(_as_int(input_data.get("joystick_button"), 1) or 1),
            poll_hz=_as_float(input_data.get("poll_hz"), 60.0),
        ),
        push_to_talk=PushToTalkConfig(
            enabled=_as_bool(ptt_data.get("enabled"), True),
            hotkey=ptt_hotkey,
            release_grace_ms=int(_as_int(ptt_data.get("release_grace_ms"), 300) or 300),
            pre_roll_ms=ptt_pre_roll,
            max_context_ms=ptt_max_context,
        ),
        udp_reliability=_parse_udp_reliability(data),
        dashboard_privacy=_parse_dashboard_privacy(data),
        stt=SttConfig(
            engine=_as_str(stt_data.get("engine"), "whisper_cpp").lower(),
            model_path=_as_str(stt_data.get("model_path"), "models/whisper/ggml-base.en.bin"),
            sample_rate=int(_as_int(stt_data.get("sample_rate"), 16000) or 16000),
            device=stt_data.get("device", _as_dict(stt_data.get("vosk", {})).get("device")),
            language=_as_str(stt_data.get("language"), selected_language).lower(),
            whisper_engine=_as_str(whisper_data.get("engine"), "auto").lower(),
            cli_exe=_as_str(whisper_data.get("cli_exe"), "whisper-cli"),
            threads=int(_as_int(whisper_data.get("threads"), 4) or 4),
            beam_size=int(_as_int(whisper_data.get("beam_size"), 1) or 1),
            pre_roll_ms=ptt_pre_roll,
            max_context_ms=ptt_max_context,
            highpass_hz=_as_float(whisper_data.get("highpass_hz"), 120.0),
            lowpass_hz=_as_float(whisper_data.get("lowpass_hz"), 7600.0),
            cli_timeout_seconds=_as_float(whisper_data.get("cli_timeout_seconds"), 30.0),
        ),
        llm=LlmConfig(
            provider=_as_str(llm_data.get("provider"), "ollama").lower(),
            base_url=_as_str(llm_data.get("base_url"), "http://127.0.0.1:11434"),
            model=_as_str(llm_data.get("model"), "qwen2.5:0.5b"),
            recommended_model=_as_str(llm_data.get("recommended_model"), "qwen2.5:1.5b"),
            high_quality_model=_as_str(llm_data.get("high_quality_model"), "llama3.2:3b"),
            timeout_seconds=_as_float(llm_data.get("timeout_seconds"), 8.0),
        ),
        tts=TtsConfig(
            engine=_as_str(tts_data.get("engine"), "piper").lower(),
            piper_exe=_as_str(tts_data.get("piper_exe"), "piper"),
            piper_model=_as_str(tts_data.get("piper_model"), "models/piper/en_US-lessac-low.onnx"),
            optional_male_model=_as_str(tts_data.get("optional_male_model"), "models/piper/en_US-ryan-low.onnx"),
            language=_as_str(tts_data.get("language"), selected_language).lower(),
            bandpass_low_hz=_as_float(radio_filter.get("bandpass_low_hz"), 300.0),
            bandpass_high_hz=_as_float(radio_filter.get("bandpass_high_hz"), 3000.0),
            static_level=_as_float(radio_filter.get("static_level"), 0.012),
            piper_timeout_seconds=_as_float(tts_data.get("piper_timeout_seconds"), 30.0),
        ),
        commands=commands,
    )


def resolve_bridge_runtime_config(
    app_config: AppConfig,
    *,
    host: str | None = None,
    port: int | None = None,
    telemetry_host: str | None = None,
    telemetry_port: int | None = None,
    ptt_hotkey: str | None = None,
    joystick_index: int | None = None,
    joystick_button: int | None = None,
    enable_input_manager: bool | None = None,
) -> BridgeRuntimeConfig:
    """Resolve runtime WebRTC/input values with CLI arguments taking precedence."""

    ptt_enabled = app_config.push_to_talk.enabled
    keyboard_enabled = ptt_enabled and app_config.input.keyboard_enabled
    joystick_enabled = ptt_enabled and app_config.input.joystick_enabled
    if enable_input_manager is False:
        keyboard_enabled = False
        joystick_enabled = False

    return BridgeRuntimeConfig(
        host=host if host is not None else app_config.webrtc.host,
        port=port if port is not None else app_config.webrtc.port,
        telemetry_host=telemetry_host if telemetry_host is not None else app_config.telemetry.host,
        telemetry_port=telemetry_port if telemetry_port is not None else app_config.telemetry.port,
        ptt_hotkey=ptt_hotkey if ptt_hotkey is not None else app_config.push_to_talk.hotkey,
        joystick_index=joystick_index if joystick_index is not None else app_config.input.joystick_index,
        joystick_button=joystick_button if joystick_button is not None else app_config.input.joystick_button,
        keyboard_enabled=keyboard_enabled,
        joystick_enabled=joystick_enabled,
        poll_hz=app_config.input.poll_hz,
        pre_roll_ms=app_config.push_to_talk.pre_roll_ms,
        max_context_ms=app_config.push_to_talk.max_context_ms,
        vad_rms_threshold=app_config.webrtc.vad_rms_threshold,
        vad_hangover_frames=app_config.webrtc.vad_hangover_frames,
    )
