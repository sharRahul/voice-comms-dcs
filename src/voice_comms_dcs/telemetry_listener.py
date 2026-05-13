from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

TelemetryCallback = Callable[[dict[str, Any]], None]


@dataclass
class TelemetrySnapshot:
    """Latest DCS telemetry packet with receive metadata."""

    data: dict[str, Any] = field(default_factory=dict)
    received_at: float = 0.0
    source: tuple[str, int] | None = None

    @property
    def age_seconds(self) -> float:
        if self.received_at <= 0:
            return float("inf")
        return time.monotonic() - self.received_at


class TelemetryListener:
    """Receives JSON-over-UDP telemetry from DCS Export.lua.

    The listener is intentionally lightweight: one UDP socket, one background thread, no blocking
    callbacks in the receive loop. Heavy AI processing should read the latest snapshot or use a
    fast callback that passes work to another queue.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 10309,
        on_telemetry: TelemetryCallback | None = None,
        max_packet_size: int = 8192,
    ) -> None:
        self.host = host
        self.port = port
        self.on_telemetry = on_telemetry
        self.max_packet_size = max_packet_size
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest = TelemetrySnapshot()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.host, self.port))
        self._socket.settimeout(0.25)
        self._thread = threading.Thread(target=self._run, name="dcs-telemetry-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._socket:
            self._socket.close()
            self._socket = None

    def latest(self) -> TelemetrySnapshot:
        with self._lock:
            return TelemetrySnapshot(
                data=dict(self._latest.data),
                received_at=self._latest.received_at,
                source=self._latest.source,
            )

    def _run(self) -> None:
        assert self._socket is not None
        while not self._stop_event.is_set():
            try:
                packet, source = self._socket.recvfrom(self.max_packet_size)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                decoded = packet.decode("utf-8")
                telemetry = json.loads(decoded)
                if not isinstance(telemetry, dict):
                    continue
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue

            snapshot = TelemetrySnapshot(
                data=telemetry,
                received_at=time.monotonic(),
                source=source,
            )
            with self._lock:
                self._latest = snapshot

            if self.on_telemetry:
                try:
                    self.on_telemetry(telemetry)
                except Exception:
                    # Telemetry ingestion must never crash the listener.
                    continue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Listen for DCS JSON telemetry packets.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=10309)
    args = parser.parse_args(argv)

    listener = TelemetryListener(host=args.host, port=args.port)
    listener.start()
    print(f"Listening for DCS telemetry on UDP {args.host}:{args.port}")
    try:
        while True:
            snapshot = listener.latest()
            if snapshot.data:
                print(json.dumps(snapshot.data, indent=2, sort_keys=True))
            time.sleep(1.0)
    except KeyboardInterrupt:
        listener.stop()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
