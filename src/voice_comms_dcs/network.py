from __future__ import annotations

import socket
from dataclasses import dataclass

from .config import Action, VoiceCommand

PROTOCOL_PREFIX = "VCDCS"


@dataclass(frozen=True)
class UdpTarget:
    host: str
    port: int


class DcsUdpClient:
    """Tiny UDP client used to send matched commands to the DCS Lua bridge."""

    def __init__(self, target: UdpTarget) -> None:
        self.target = target
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def close(self) -> None:
        self._socket.close()

    def send_command(self, command: VoiceCommand) -> str:
        payload = encode_payload(command.id, command.action)
        self._socket.sendto(payload.encode("utf-8"), (self.target.host, self.target.port))
        return payload


def encode_payload(command_id: str, action: Action) -> str:
    if action.type == "flag":
        if action.flag is None or action.value is None:
            raise ValueError("Flag action requires flag and value.")
        return f"{PROTOCOL_PREFIX}|{command_id}|flag|{action.flag}|{action.value}"

    if action.type == "command":
        if not action.command:
            raise ValueError("Command action requires command text.")
        safe_command = action.command.replace("|", " ").strip()
        return f"{PROTOCOL_PREFIX}|{command_id}|command|{safe_command}"

    raise ValueError(f"Unsupported action type: {action.type}")
