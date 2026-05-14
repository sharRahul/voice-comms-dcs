from __future__ import annotations

import asyncio
import time

from voice_comms_dcs.api_routes import DashboardEventHub


class FakeWebSocket:
    def __init__(self, *, delay: float = 0.0, fail: bool = False) -> None:
        self.delay = delay
        self.fail = fail
        self.sent: list[str] = []

    async def send_str(self, message: str) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ConnectionError("broken")
        self.sent.append(message)


def test_broadcast_sends_to_all_clients():
    async def run() -> None:
        hub = DashboardEventHub(send_timeout_seconds=0.1)
        one = FakeWebSocket()
        two = FakeWebSocket()
        await hub.connect(one)  # type: ignore[arg-type]
        await hub.connect(two)  # type: ignore[arg-type]
        await hub.broadcast({"type": "ok"})
        assert len(one.sent) == 1
        assert len(two.sent) == 1

    asyncio.run(run())


def test_failing_client_is_disconnected_without_raising():
    async def run() -> None:
        hub = DashboardEventHub(send_timeout_seconds=0.1)
        good = FakeWebSocket()
        bad = FakeWebSocket(fail=True)
        await hub.connect(good)  # type: ignore[arg-type]
        await hub.connect(bad)  # type: ignore[arg-type]
        await hub.broadcast({"type": "ok"})
        await hub.broadcast({"type": "again"})
        assert len(good.sent) == 2

    asyncio.run(run())


def test_slow_client_timeout_does_not_block_normal_client():
    async def run() -> None:
        hub = DashboardEventHub(send_timeout_seconds=0.02)
        good = FakeWebSocket()
        slow = FakeWebSocket(delay=0.2)
        await hub.connect(good)  # type: ignore[arg-type]
        await hub.connect(slow)  # type: ignore[arg-type]
        started = time.perf_counter()
        await hub.broadcast({"type": "ok"})
        elapsed = time.perf_counter() - started
        assert len(good.sent) == 1
        assert elapsed < 0.15

    asyncio.run(run())
