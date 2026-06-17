import asyncio

from pana.daemon import Daemon
from pana.hw import detect as d
from pana.hw.transport import FakeSysfs
from pana.ipc.protocol import Request


def _daemon() -> Daemon:
    fs = FakeSysfs({
        d.PLATFORM_PROFILE: "performance",
        d.PLATFORM_PROFILE_CHOICES: "low-power balanced performance custom",
        d.CONSERVATION: "0",
    })
    return Daemon(fs=fs, socket_path="/tmp/unused.sock")


def test_ping():
    resp = asyncio.run(_daemon().handle(Request(cmd="ping")))
    assert resp.ok is True
    assert resp.data["pong"] is True


def test_status_returns_capabilities():
    resp = asyncio.run(_daemon().handle(Request(cmd="status")))
    assert resp.ok is True
    assert resp.data["capabilities"]["power_modes"] is True
    assert "custom" in resp.data["capabilities"]["profile_choices"]


def test_unknown_command():
    resp = asyncio.run(_daemon().handle(Request(cmd="frobnicate")))
    assert resp.ok is False
    assert "unknown" in resp.error.lower()
