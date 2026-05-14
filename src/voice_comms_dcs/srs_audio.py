from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)

VALID_MODULATIONS = {"AM", "FM"}
VALID_COALITIONS = {"blue", "red", "neutral"}
BLOCKED_COMMAND_NAMES = {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe", "bash", "sh"}
DEFAULT_COMMAND_TEMPLATE = [
    "{exe}",
    "--file",
    "{file}",
    "--freq",
    "{frequency_mhz}",
    "--modulation",
    "{modulation}",
    "--coalition",
    "{coalition}",
]


@dataclass(frozen=True)
class SrsAudioConfig:
    enabled: bool = False
    external_audio_exe: str = "C:/Program Files/DCS-SimpleRadio-Standalone/DCS-SR-ExternalAudio.exe"
    output_dir: str = "build_output/srs_external_audio"
    frequency_mhz: float = 251.0
    modulation: str = "AM"
    coalition: str = "blue"
    command_template: list[str] | None = None
    allow_custom_command_template: bool = False
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        validate_srs_config(self)


@dataclass(frozen=True)
class SrsDispatchResult:
    enabled: bool
    audio_file: Path
    command: tuple[str, ...] = ()
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    message: str = ""


class SafeFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class SrsExternalAudioAdapter:
    """Safe local adapter for SRS ExternalAudio-style transmission.

    This module intentionally does not drive the user's microphone device and does not shell out
    through `cmd.exe`. It prepares the radio-effect audio file and can invoke a user-configurable
    local external-audio executable with explicit argv tokens.
    """

    def __init__(self, config: SrsAudioConfig | None = None) -> None:
        self.config = config or SrsAudioConfig()

    @classmethod
    def from_json(cls, path: str | Path) -> "SrsExternalAudioAdapter":
        file_path = Path(path)
        defaults = SrsAudioConfig()
        data = json.loads(file_path.read_text(encoding="utf-8")) if file_path.exists() else {}
        allow_custom_template = bool(data.get("allow_custom_command_template", defaults.allow_custom_command_template))

        command_template: list[str] | None = None
        template_data = data.get("command_template")
        if template_data is not None:
            if allow_custom_template:
                command_template = _coerce_template(template_data)
            else:
                LOGGER.warning(
                    "Ignoring SRS command_template because allow_custom_command_template is false."
                )

        return cls(
            SrsAudioConfig(
                enabled=bool(data.get("enabled", defaults.enabled)),
                external_audio_exe=str(data.get("external_audio_exe", defaults.external_audio_exe)),
                output_dir=str(data.get("output_dir", defaults.output_dir)),
                frequency_mhz=float(data.get("frequency_mhz", defaults.frequency_mhz)),
                modulation=str(data.get("modulation", defaults.modulation)).upper(),
                coalition=str(data.get("coalition", defaults.coalition)).lower(),
                command_template=command_template,
                allow_custom_command_template=allow_custom_template,
                timeout_seconds=float(data.get("timeout_seconds", defaults.timeout_seconds)),
            )
        )

    def prepare_audio_file(self, source_wav: str | Path, callsign: str = "nimbus") -> Path:
        source = Path(source_wav)
        if not source.exists():
            raise FileNotFoundError(f"Audio file not found: {source}")
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)
        target = output_dir / f"{callsign}_{timestamp}{source.suffix.lower()}"
        shutil.copy2(source, target)
        return target

    def dispatch_wav(self, source_wav: str | Path, callsign: str = "nimbus") -> SrsDispatchResult:
        audio_file = self.prepare_audio_file(source_wav, callsign=callsign)
        if not self.config.enabled:
            return SrsDispatchResult(
                enabled=False,
                audio_file=audio_file,
                message="SRS adapter disabled; audio file prepared only.",
            )

        exe = Path(self.config.external_audio_exe)
        if not exe.exists():
            return SrsDispatchResult(
                enabled=True,
                audio_file=audio_file,
                message="SRS external audio executable not found.",
            )

        command = self._build_command(audio_file)
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.config.timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return SrsDispatchResult(
                enabled=True,
                audio_file=audio_file,
                command=tuple(command),
                returncode=None,
                stdout="",
                stderr="",
                message="SRS external audio command timed out.",
            )
        return SrsDispatchResult(
            enabled=True,
            audio_file=audio_file,
            command=tuple(command),
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
            message="SRS external audio command executed." if process.returncode == 0 else "SRS external audio command failed.",
        )

    def _build_command(self, audio_file: Path) -> list[str]:
        mapping = SafeFormatDict(
            exe=self.config.external_audio_exe,
            file=str(audio_file),
            frequency_mhz=f"{self.config.frequency_mhz:.3f}",
            modulation=self.config.modulation.upper(),
            coalition=self.config.coalition.lower(),
        )
        template = self.config.command_template if self.config.allow_custom_command_template else None
        if template is None:
            template = DEFAULT_COMMAND_TEMPLATE
        return [str(token).format_map(mapping) for token in template]


def validate_srs_config(config: SrsAudioConfig) -> None:
    exe = str(config.external_audio_exe).strip()
    if not exe:
        raise ValueError("SRS external_audio_exe must not be empty.")
    exe_name = Path(exe).name.lower()
    if exe_name in BLOCKED_COMMAND_NAMES:
        raise ValueError(f"SRS external_audio_exe is blocked: {exe_name}")
    if Path(exe).suffix and Path(exe).suffix.lower() != ".exe":
        raise ValueError("SRS external_audio_exe must be an .exe path when a file suffix is provided.")

    if not 1.0 <= float(config.frequency_mhz) <= 1000.0:
        raise ValueError("SRS frequency_mhz must be between 1.0 and 1000.0.")
    if config.modulation.upper() not in VALID_MODULATIONS:
        raise ValueError(f"SRS modulation must be one of {sorted(VALID_MODULATIONS)}.")
    if config.coalition.lower() not in VALID_COALITIONS:
        raise ValueError(f"SRS coalition must be one of {sorted(VALID_COALITIONS)}.")
    if float(config.timeout_seconds) <= 0:
        raise ValueError("SRS timeout_seconds must be positive.")

    if config.command_template is not None:
        if not config.allow_custom_command_template:
            raise ValueError("SRS command_template requires allow_custom_command_template=true.")
        validate_command_template(config.command_template, exe)


def validate_command_template(template: list[str], configured_exe: str) -> None:
    if not template:
        raise ValueError("SRS command_template must not be empty.")
    for token in template:
        if not isinstance(token, str) or not token.strip():
            raise ValueError("SRS command_template tokens must be non-empty strings.")

    first_token = template[0]
    if first_token not in {"{exe}", configured_exe}:
        raise ValueError("SRS command_template first token must be {exe} or the configured executable path.")

    rendered_name = Path(first_token.replace("{exe}", configured_exe)).name.lower()
    if rendered_name in BLOCKED_COMMAND_NAMES:
        raise ValueError(f"SRS command_template executable is blocked: {rendered_name}")


def _coerce_template(template_data: Any) -> list[str]:
    if not isinstance(template_data, list):
        raise ValueError("SRS command_template must be a JSON list of argv tokens.")
    return [str(token) for token in template_data]


def load_default_adapter(path: str | Path = "config/srs/srs_audio.json") -> SrsExternalAudioAdapter:
    return SrsExternalAudioAdapter.from_json(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare or dispatch a Nimbus radio WAV through an SRS ExternalAudio-style adapter.")
    parser.add_argument("--config", default="config/srs/srs_audio.json")
    parser.add_argument("--wav", required=True)
    parser.add_argument("--callsign", default="nimbus")
    args = parser.parse_args(argv)

    adapter = SrsExternalAudioAdapter.from_json(args.config)
    result = adapter.dispatch_wav(args.wav, callsign=args.callsign)
    print(json.dumps({
        "enabled": result.enabled,
        "audio_file": str(result.audio_file),
        "command": list(result.command),
        "returncode": result.returncode,
        "message": result.message,
        "stderr": result.stderr,
    }, indent=2))
    if result.returncode is None or result.returncode == 0:
        return 0
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
