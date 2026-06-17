import pytest

from pana.core.config import Config, State
from pana.core.manager import Manager
from pana.hw import detect as d
from pana.hw.cpufreq import MAX_PERF_PCT
from pana.hw.hid import FakeHid
from pana.hw.spectrum import OP_GET_BRIGHTNESS
from pana.hw.transport import FakeSysfs


def _fs() -> FakeSysfs:
    return FakeSysfs({
        d.PLATFORM_PROFILE: "performance",
        d.PLATFORM_PROFILE_CHOICES: "low-power balanced balanced-performance performance custom",
        d.CONSERVATION: "0",
        "/sys/class/power_supply/BAT0/capacity": "38",
        "/sys/class/power_supply/BAT0/status": "Charging",
        "/sys/class/hidraw/hidraw4/device/uevent": "HID_ID=0003:0000048D:0000C197\n",
        MAX_PERF_PCT: "100",
    })


def _opener():
    dev = FakeHid({OP_GET_BRIGHTNESS: bytes([0x07, 0, 0, 0, 5])})
    return lambda path: dev, dev


def _manager(state=None):
    opener, _dev = _opener()
    return Manager(fs=_fs(), lights_opener=opener, config=Config(), state=state or State())


def test_apply_mode_eco_caps_clock_and_sets_battery_lights():
    fs = _fs()
    opener, dev = _opener()
    m = Manager(fs=fs, lights_opener=opener)
    st = m.apply_mode("eco")
    assert fs.read(d.PLATFORM_PROFILE) == "low-power"
    assert fs.read(MAX_PERF_PCT) == "55"   # eco_max_perf_pct default -> the real cooling cap
    assert fs.read(d.CONSERVATION) == "1"
    assert st["mode"] == "eco"
    assert st["cpu_cap"]["desired_pct"] == 55
    assert dev.sent[-1][:5] == bytes([0x07, 0xCE, 0xC0, 0x03, 0])  # lights off


def test_apply_mode_game_uncaps_clock():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    m.apply_mode("eco")                   # cap first
    st = m.apply_mode("game")
    assert fs.read(d.PLATFORM_PROFILE) == "performance"
    assert fs.read(MAX_PERF_PCT) == "100"  # ceiling lifted
    assert fs.read(d.CONSERVATION) == "0"
    assert st["cpu_cap"]["desired_pct"] is None


def test_apply_mode_unknown_raises():
    with pytest.raises(ValueError):
        _manager().apply_mode("ludicrous")


def test_set_power_caps_clock_and_clamps():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    st = m.set_power(40)
    assert fs.read(MAX_PERF_PCT) == "40"
    assert st["mode"] == "custom"
    assert m.state.custom_max_pct == 40
    assert st["cpu_cap"]["desired_pct"] == 40


def test_set_power_floor_clamp():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    m.set_power(1)
    assert fs.read(MAX_PERF_PCT) == "10"   # FLOOR_PCT


def test_enforce_cap_pushes_down_after_thermald_raises():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    m.apply_mode("eco")                    # cap to 55%
    fs.write(MAX_PERF_PCT, "100")          # pretend something raised the ceiling
    m.enforce_cap()
    assert fs.read(MAX_PERF_PCT) == "55"   # re-asserted down


def test_enforce_cap_noop_when_uncapped():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    m.apply_mode("game")                   # uncapped
    fs.write(MAX_PERF_PCT, "100")
    n_writes = len(fs.writes)
    m.enforce_cap()
    assert len(fs.writes) == n_writes


def test_reapply_custom_restores_clock_cap():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0], state=State(mode="custom", custom_max_pct=50))
    m.reapply()
    assert fs.read(MAX_PERF_PCT) == "50"
    assert m._desired_pct == 50


def test_set_battery_target_records_and_caps_when_at_target():
    fs = _fs()
    fs._files["/sys/class/power_supply/BAT0/capacity"] = "90"
    m = Manager(fs=fs, lights_opener=_opener()[0])
    st = m.set_battery(target=85)
    assert st["battery"]["soft_target"] == 85
    assert fs.read(d.CONSERVATION) == "1"


def test_status_shape():
    st = _manager().status()
    assert st["platform_profile"] == "performance"
    assert "custom" in st["profile_choices"]
    assert st["battery"]["capacity"] == 38
    assert st["lights"]["available"] is True
    assert st["cpu_cap"]["available"] is True
    assert st["cpu_cap"]["max_perf_pct"] == 100


def test_lights_on_honors_explicit_brightness():
    fs = _fs()
    dev = FakeHid({OP_GET_BRIGHTNESS: bytes([0x07, 0, 0, 0, 5])})
    m = Manager(fs=fs, lights_opener=lambda p: dev, config=Config(light_on_brightness=3))
    m.set_lights(on=True, brightness=7)
    assert dev.sent[-1][:5] == bytes([0x07, 0xCE, 0xC0, 0x03, 7])


def test_status_battery_honesty_fields():
    m = _manager()
    st = m.status()["battery"]
    assert st["firmware_cap_floor"] is True
    assert st["reverts_to_charging_if_daemon_stops"] is True
    assert st["soft_target_note"] is None
    m.set_battery(target=85)
    assert m.status()["battery"]["soft_target_note"] is not None


def test_night_enabled_inherits_config_then_state_override():
    m = Manager(fs=_fs(), lights_opener=_opener()[0], config=Config(night_enabled=True))
    assert m.night_enabled() is True
    m.set_night(enabled=False)
    assert m.night_enabled() is False
