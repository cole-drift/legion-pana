from pana.core.config import Config, State
from pana.core.manager import Manager
from pana.hw import detect as d
from pana.hw.hid import FakeHid
from pana.hw.spectrum import OP_GET_BRIGHTNESS
from pana.hw.transport import FakeSysfs


def _fs() -> FakeSysfs:
    return FakeSysfs({
        d.PLATFORM_PROFILE: "performance",
        d.PLATFORM_PROFILE_CHOICES: "low-power balanced balanced-performance performance custom",
        f"{d.PPT_DIR}/ppt_pl1_spl/current_value": "0",
        f"{d.PPT_DIR}/ppt_pl1_spl/min_value": "50",
        f"{d.PPT_DIR}/ppt_pl1_spl/max_value": "110",
        f"{d.PPT_DIR}/ppt_pl2_sppt/current_value": "0",
        f"{d.PPT_DIR}/ppt_pl2_sppt/min_value": "60",
        f"{d.PPT_DIR}/ppt_pl2_sppt/max_value": "168",
        d.CONSERVATION: "0",
        "/sys/class/power_supply/BAT0/capacity": "38",
        "/sys/class/power_supply/BAT0/status": "Charging",
        "/sys/class/hidraw/hidraw4/device/uevent": "HID_ID=0003:0000048D:0000C197\n",
    })


def _opener():
    dev = FakeHid({OP_GET_BRIGHTNESS: bytes([0x07, 0, 0, 0, 5])})
    return lambda path: dev, dev


def _manager(state=None):
    opener, _dev = _opener()
    return Manager(fs=_fs(), lights_opener=opener, config=Config(), state=state or State())


def test_apply_mode_eco_sets_profile_battery_lights():
    fs = _fs()
    opener, dev = _opener()
    m = Manager(fs=fs, lights_opener=opener)
    st = m.apply_mode("eco")
    assert fs.read(d.PLATFORM_PROFILE) == "low-power"
    assert fs.read(d.CONSERVATION) == "1"
    assert st["mode"] == "eco"
    # lights off => set-brightness 0 was the last sent report
    assert dev.sent[-1][:5] == bytes([0x07, 0xCE, 0xC0, 0x03, 0])


def test_apply_mode_game():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    m.apply_mode("game")
    assert fs.read(d.PLATFORM_PROFILE) == "performance"
    assert fs.read(d.CONSERVATION) == "0"


def test_apply_mode_unknown_raises():
    import pytest
    with pytest.raises(ValueError):
        _manager().apply_mode("ludicrous")


def test_set_tdp_enters_custom_and_clamps():
    fs = _fs()
    m = Manager(fs=fs, lights_opener=_opener()[0])
    m.set_tdp(pl1=10, pl2=999)
    assert fs.read(d.PLATFORM_PROFILE) == "custom"
    assert fs.read(f"{d.PPT_DIR}/ppt_pl1_spl/current_value") == "50"   # clamped up
    assert fs.read(f"{d.PPT_DIR}/ppt_pl2_sppt/current_value") == "168"  # clamped down


def test_set_battery_target_records_and_caps_when_at_target():
    fs = _fs()
    fs.write(d.CONSERVATION, "0")
    fs._files["/sys/class/power_supply/BAT0/capacity"] = "90"
    m = Manager(fs=fs, lights_opener=_opener()[0])
    st = m.set_battery(target=85)
    assert st["battery"]["soft_target"] == 85
    assert fs.read(d.CONSERVATION) == "1"  # already above target -> capped now


def test_status_shape():
    st = _manager().status()
    assert st["platform_profile"] == "performance"
    assert "custom" in st["profile_choices"]
    assert st["battery"]["capacity"] == 38
    assert st["lights"]["available"] is True
    assert set(st["ppt"]) == {"ppt_pl1_spl", "ppt_pl2_sppt"}


def test_night_enabled_inherits_config_then_state_override():
    opener = _opener()[0]
    m = Manager(fs=_fs(), lights_opener=opener, config=Config(night_enabled=True))
    assert m.night_enabled() is True
    m.set_night(enabled=False)
    assert m.night_enabled() is False
