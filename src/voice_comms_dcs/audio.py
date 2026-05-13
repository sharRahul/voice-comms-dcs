from __future__ import annotations

from dataclasses import dataclass

import sounddevice as sd


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    max_input_channels: int
    default_sample_rate: float


def list_input_devices() -> list[AudioDevice]:
    """Return available microphone/input devices for future UI selection support."""
    devices: list[AudioDevice] = []
    for index, device in enumerate(sd.query_devices()):
        max_input_channels = int(device.get("max_input_channels", 0))
        if max_input_channels <= 0:
            continue
        devices.append(
            AudioDevice(
                index=index,
                name=str(device.get("name", f"Device {index}")),
                max_input_channels=max_input_channels,
                default_sample_rate=float(device.get("default_samplerate", 16000.0)),
            )
        )
    return devices
