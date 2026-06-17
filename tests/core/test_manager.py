import pytest

from pana.core.config import Config, State
from pana.core.manager import Manager
from pana.hw import detect as d
from pana.hw.hid import FakeHid
from pana.hw.rapl import PL1, PL1_MAX, PL2, PL2_MAX
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
        "/sys/class/powercap/intel-rapl:0/name": "package-0",
        PL1: "115000000",
        PL2: "168000000",
        PL1_MAX: "120000000",
        PL2_MAX: "224000000",
    })


def _opener():
    dev = FakeHid({OP_GET_BRIGHTNESS: bytes([0x07, 0, 0, 0, 5])})
    return lambda path: dev, dev


def _manager(state=None):
    opener, _dev = _opener()
    return Manager(fs=_fs(), lights_opener=opener, config=Config(), state=state or State())


def test_apply_mode_eco_caps_rapl_and_sets_battery_lights():
    fs = _fs()
    opener, dev = _opener()
    m = Manager(fs=fs, lights_opener=opener)
    st = m.apply_mode("eco")
    assert fs.read(d.PLATFORM_PROFILE) == "low-power"
    assert fs.read(PL1) == "45000000"   # eco_pl1_w default 45W -> the real cooling cap
    assert fs.read(PL2) == "60000000"
    assert fs.read(d.CONSERVATION) == "1"
    assert st["mode"] == "eco"
    assert st["rapl"]["desired_w"] == {"pl1": 45.0, "pl2": 60.0}
    assert dev.sent[-1][:5] == bytes([0x07, 0xCE, 0xC0, 0x03, 0])  # lights off


def test_apply_mode_game_uncaps_rapl():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    # first cap via eco, then game must lift it
    m.apply_mode("eco")
    st = m.apply_mode("game")
    assert fs.read(d.PLATFORM_PROFILE) == "performance"
    assert fs.read(PL1) == "115000000"   # restored to stock
    assert fs.read(d.CONSERVATION) == "0"
    assert st["rapl"]["desired_w"] is None   # not enforced when uncapped


def test_apply_mode_unknown_raises():
    with pytest.raises(ValueError):
        _manager().apply_mode("ludicrous")


def test_set_tdp_caps_via_rapl_and_clamps():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    st = m.set_tdp(pl1=40, pl2=999)
    assert fs.read(PL1) == "40000000"     # 40W applied
    assert fs.read(PL2) == "224000000"    # clamped to PL2 max
    assert st["mode"] == "custom"
    assert m.state.custom_pl1 == 40.0
    assert st["rapl"]["desired_w"]["pl1"] == 40.0


def test_set_tdp_floor_clamp():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    m.set_tdp(pl1=1)
    assert fs.read(PL1) == "8000000"      # FLOOR_W


def test_enforce_rapl_pushes_down_after_thermald_raises():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    m.apply_mode("eco")                   # cap PL1 to 45W
    fs.write(PL1, "115000000")            # pretend thermald reset it to stock
    m.enforce_rapl()
    assert fs.read(PL1) == "45000000"     # re-asserted down to the cap


def test_enforce_rapl_noop_when_uncapped():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    m.apply_mode("game")                  # uncapped -> not enforced
    fs.write(PL1, "115000000")
    n_writes = len(fs.writes)
    m.enforce_rapl()
    assert len(fs.writes) == n_writes     # nothing written


def test_reapply_custom_restores_rapl_caps():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0], state=State(mode="custom", custom_pl1=50.0))
    m.reapply()
    assert fs.read(PL1) == "50000000"
    assert m._desired_rapl == {"pl1": 50.0}


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
    assert st["rapl"]["available"] is True
    assert st["rapl"]["limits_w"]["pl1"] == 115.0


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
