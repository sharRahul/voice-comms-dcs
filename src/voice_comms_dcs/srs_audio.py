from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SrsAudioConfig:
    enabled: bool = False
    external_audio_exe: str = "C:/Program Files/DCS-SimpleRadio-Standalone/DCS-SR-ExternalAudio.exe"
    output_dir: str = "build_output/srs_external_audio"
    frequency_mhz: float = 251.0
    modulation: str = "AM"
    coalition: str = "blue"
    command_template: list[str] | None = None
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class SrsDispatchResult:
    enabled: bool
    audio_file: Path
    command: tuple[str, ...] = ()
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    message: str = ""


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
        template_data = data.get("command_template", DEFAULT_COMMAND_TEMPLATE)
        command_template = template_data if isinstance(template_data, list) else DEFAULT_COMMAND_TEMPLATE
        return cls(
            SrsAudioConfig(
                enabled=bool(data.get("enabled", defaults.enabled)),
                external_audio_exe=str(data.get("external_audio_exe", defaults.external_audio_exe)),
                output_dir=str(data.get("output_dir", defaults.output_dir)),
                frequency_mhz=float(data.get("frequency_mhz", defaults.frequency_mhz)),
                modulation=str(data.get("modulation", defaults.modulation)).upper(),
                coalition=str(data.get("coalition", defaults.coalition)).lower(),
                command_template=list(command_template),
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
                message=f"SRS external audio executable not found: {exe}",
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
            modulation=self.config.modulation,
            coalition=self.config.coalition,
        )
        template = self.config.command_template or DEFAULT_COMMAND_TEMPLATE
        return [str(token).format_map(mapping) for token in template]


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
    return 0 if result.returncode in {None, 0} else int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
