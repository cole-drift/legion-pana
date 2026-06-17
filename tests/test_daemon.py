import asyncio
from datetime import time

from pana.core.config import Config, State
from pana.daemon import Daemon
from pana.hw import detect as d
from pana.hw.hid import FakeHid
from pana.hw.spectrum import OP_GET_BRIGHTNESS
from pana.hw.transport import FakeSysfs
from pana.ipc.protocol import Request


def _fs() -> FakeSysfs:
    return FakeSysfs({
        d.PLATFORM_PROFILE: "performance",
        d.PLATFORM_PROFILE_CHOICES: "low-power balanced balanced-performance performance custom",
        f"{d.PPT_DIR}/ppt_pl1_spl/current_value": "0",
        f"{d.PPT_DIR}/ppt_pl1_spl/min_value": "50",
        f"{d.PPT_DIR}/ppt_pl1_spl/max_value": "110",
        d.CONSERVATION: "0",
        "/sys/class/power_supply/BAT0/capacity": "38",
        "/sys/class/hidraw/hidraw4/device/uevent": "HID_ID=0003:0000048D:0000C197\n",
    })


def _daemon(config=None):
    dev = FakeHid({OP_GET_BRIGHTNESS: bytes([0x07, 0, 0, 0, 5])})
    return Daemon(
        fs=_fs(),
        lights_opener=lambda path: dev,
        socket_path="/tmp/unused.sock",
        config=config or Config(),
        state=State(),
    )


def _call(daemon, cmd, **args):
    return asyncio.run(daemon.handle(Request(cmd=cmd, args=args)))


def test_ping():
    assert _call(_daemon(), "ping").data == {"pong": True}


def test_status_includes_caps_and_monitor_slot():
    resp = _call(_daemon(), "status")
    assert resp.ok
    assert resp.data["platform_profile"] == "performance"
    assert resp.data["capabilities"]["power_modes"] is True
    assert "monitor" in resp.data  # None until a sample is taken


def test_mode_command_applies():
    daemon = _daemon()
    resp = _call(daemon, "mode", name="eco")
    assert resp.ok
    assert resp.data["mode"] == "eco"
    assert daemon.manager.fs.read(d.PLATFORM_PROFILE) == "low-power"


def test_tdp_command_clamps():
    daemon = _daemon()
    resp = _call(daemon, "tdp", pl1=10)
    assert resp.ok
    assert daemon.manager.fs.read(f"{d.PPT_DIR}/ppt_pl1_spl/current_value") == "50"


def test_battery_target_command():
    daemon = _daemon()
    resp = _call(daemon, "battery", target=85)
    assert resp.data["battery"]["soft_target"] == 85


def test_lights_off_command():
    daemon = _daemon()
    resp = _call(daemon, "lights", on=False)
    assert resp.ok
    assert resp.data["lights"]["manual"] == "off"


def test_unknown_command():
    resp = _call(_daemon(), "frobnicate")
    assert resp.ok is False
    assert "unknown" in resp.error.lower()


def test_handler_error_is_caught():
    resp = _call(_daemon(), "mode", name="does-not-exist")
    assert resp.ok is False
    assert "unknown mode" in resp.error.lower()


def test_scheduler_tick_turns_off_at_night_then_idempotent():
    daemon = _daemon(config=Config(night_enabled=True, night_start="20:00", night_end="07:00"))
    assert daemon._scheduler_tick(now_t=time(23, 0)) == "off"
    assert daemon._scheduler_tick(now_t=time(23, 30)) is None  # unchanged


def test_scheduler_manual_override_beats_schedule():
    daemon = _daemon(config=Config(night_enabled=True, night_start="20:00", night_end="07:00"))
    daemon.manager.state.lights_manual = "on"
    assert daemon._scheduler_tick(now_t=time(23, 0)) == "on"
