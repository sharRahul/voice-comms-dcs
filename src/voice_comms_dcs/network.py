from __future__ import annotations

import logging
import socket
from dataclasses import dataclass

from .config import Action, UdpReliabilityConfig, VoiceCommand

PROTOCOL_PREFIX = "VCDCS"
ACK_PREFIX = "VCDCS_ACK"
_MAX_SEQUENCE = 2_147_483_647
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UdpTarget:
    host: str
    port: int


class DcsUdpClient:
    """Tiny UDP client used to send matched commands to the DCS Lua bridge."""

    def __init__(
        self,
        target: UdpTarget,
        reliability: UdpReliabilityConfig | None = None,
        sock: socket.socket | None = None,
    ) -> None:
        self.target = target
        self.reliability = reliability or UdpReliabilityConfig()
        self._socket = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sequence = 0
        self.last_ack_status: str | None = None

    def close(self) -> None:
        self._socket.close()

    def send_command(self, command: VoiceCommand) -> str:
        if self.reliability.enabled and self.reliability.protocol_version >= 2:
            sequence = self._next_sequence()
            payload = encode_payload_v2(command.id, command.action, sequence)
            self._send_payload(payload, sequence)
            return payload

        payload = encode_payload(command.id, command.action)
        self._socket.sendto(payload.encode("utf-8"), (self.target.host, self.target.port))
        self.last_ack_status = None
        return payload

    def _next_sequence(self) -> int:
        self._sequence = 1 if self._sequence >= _MAX_SEQUENCE else self._sequence + 1
        return self._sequence

    def _send_payload(self, payload: str, sequence: int) -> None:
        encoded = payload.encode("utf-8")
        target = (self.target.host, self.target.port)
        self.last_ack_status = None

        if not self.reliability.require_ack:
            self._socket.sendto(encoded, target)
            return

        attempts = max(1, self.reliability.retries + 1)
        previous_timeout = None
        if hasattr(self._socket, "gettimeout"):
            previous_timeout = self._socket.gettimeout()
        if hasattr(self._socket, "settimeout"):
            self._socket.settimeout(self.reliability.ack_timeout_seconds)
        try:
            for attempt in range(attempts):
                self._socket.sendto(encoded, target)
                ack = self._receive_ack(sequence)
                if ack == "ok":
                    self.last_ack_status = "ok"
                    return
                if ack and ack.startswith("rejected"):
                    self.last_ack_status = ack
                    logger.warning("DCS UDP command rejected by Lua bridge: %s", ack)
                    return
                if attempt + 1 < attempts:
                    continue
            self.last_ack_status = "timeout"
            logger.warning("No DCS UDP acknowledgement received for sequence %s", sequence)
        finally:
            if hasattr(self._socket, "settimeout"):
                self._socket.settimeout(previous_timeout)

    def _receive_ack(self, sequence: int) -> str | None:
        try:
            data, _addr = self._socket.recvfrom(1024)
        except socket.timeout:
            return None
        except TimeoutError:
            return None
        except OSError:
            return None

        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return None
        fields = text.strip().split("|")
        if len(fields) < 3 or fields[0] != ACK_PREFIX or fields[1] != str(sequence):
            return None
        if fields[2] == "ok":
            return "ok"
        if fields[2] == "rejected":
            reason = fields[3] if len(fields) > 3 else "unknown"
            return f"rejected:{reason}"
        return None


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


def encode_payload_v2(command_id: str, action: Action, sequence: int) -> str:
    legacy = encode_payload(command_id, action)
    _, *rest = legacy.split("|")
    return "|".join((PROTOCOL_PREFIX, "v2", str(int(sequence)), *rest))
