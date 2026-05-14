from __future__ import annotations

import socket

from voice_comms_dcs.config import Action, UdpReliabilityConfig, VoiceCommand
from voice_comms_dcs.network import DcsUdpClient, UdpTarget, encode_payload, encode_payload_v2


class FakeSocket:
    def __init__(self, replies: list[bytes] | None = None) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.replies = replies or []
        self.timeout = None
        self.closed = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def recvfrom(self, _size: int):
        if not self.replies:
            raise socket.timeout()
        return self.replies.pop(0), ("127.0.0.1", 10308)

    def settimeout(self, value):
        self.timeout = value

    def gettimeout(self):
        return self.timeout

    def close(self):
        self.closed = True


def test_v1_payload_format_is_unchanged():
    payload = encode_payload("request_tanker", Action("flag", flag=5101, value=1))
    assert payload == "VCDCS|request_tanker|flag|5101|1"


def test_v2_payload_includes_protocol_version_and_sequence():
    payload = encode_payload_v2("request_tanker", Action("flag", flag=5101, value=1), 42)
    assert payload == "VCDCS|v2|42|request_tanker|flag|5101|1"


def test_invalid_action_still_raises():
    try:
        encode_payload("bad", Action("bad"))
    except ValueError as exc:
        assert "Unsupported action type" in str(exc)
    else:
        raise AssertionError("invalid action did not raise")


def test_default_v2_no_ack_path_does_not_wait():
    sock = FakeSocket()
    client = DcsUdpClient(UdpTarget("127.0.0.1", 10308), sock=sock)
    payload = client.send_command(VoiceCommand("request_tanker", ("request tanker",), Action("flag", flag=1, value=1)))
    assert payload.startswith("VCDCS|v2|1|request_tanker|flag|1|1")
    assert len(sock.sent) == 1
    assert client.last_ack_status is None


def test_ack_path_records_ok():
    sock = FakeSocket([b"VCDCS_ACK|1|ok"])
    client = DcsUdpClient(
        UdpTarget("127.0.0.1", 10308),
        reliability=UdpReliabilityConfig(require_ack=True, retries=1),
        sock=sock,
    )
    client.send_command(VoiceCommand("request_tanker", ("request tanker",), Action("flag", flag=1, value=1)))
    assert len(sock.sent) == 1
    assert client.last_ack_status == "ok"


def test_ack_timeout_retries_without_hanging():
    sock = FakeSocket()
    client = DcsUdpClient(
        UdpTarget("127.0.0.1", 10308),
        reliability=UdpReliabilityConfig(require_ack=True, retries=1, ack_timeout_seconds=0.001),
        sock=sock,
    )
    client.send_command(VoiceCommand("request_tanker", ("request tanker",), Action("flag", flag=1, value=1)))
    assert len(sock.sent) == 2
    assert client.last_ack_status == "timeout"
