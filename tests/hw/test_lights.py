import pytest

from pana.hw import spectrum
from pana.hw.hid import FakeHid
from pana.hw.lights import Lights
from pana.hw.transport import FakeSysfs

_NO_FF89 = b"\x05\x01\x09\x06\xa1\x01\x05\x07"      # generic descriptor, no 0xFF89
_FF89 = b"\x06\x89\xff\x09\x07\xa1\x01\x85\x07"     # vendor usage page 0xFF89 present


def _uevent(vid: str, pid: str) -> str:
    return f"HID_ID=0003:0000{vid}:0000{pid}\nHID_NAME=Lenovo Lighting\n"


def _fs() -> FakeSysfs:
    # mirrors the live machine: hidraw2=c193, hidraw4=c197 (only c197 has the FF89 engine)
    return FakeSysfs(
        {
            "/sys/class/hidraw/hidraw2/device/uevent": _uevent("048D", "C193"),
            "/sys/class/hidraw/hidraw4/device/uevent": _uevent("048D", "C197"),
            "/sys/class/hidraw/hidraw0/device/uevent": _uevent("1234", "5678"),
        },
        binary={
            "/sys/class/hidraw/hidraw2/device/report_descriptor": _NO_FF89,
            "/sys/class/hidraw/hidraw4/device/report_descriptor": _FF89,
        },
    )


def test_candidates_prefers_c197_ff89_and_excludes_bare_c193():
    lights = Lights(_fs(), opener=lambda p: FakeHid())
    assert lights.candidates() == ["/dev/hidraw4"]


def test_connect_picks_the_effect_device():
    dev = FakeHid()
    lights = Lights(_fs(), opener=lambda p: dev if p == "/dev/hidraw4" else FakeHid())
    assert lights.connect() == "/dev/hidraw4"


def test_color_sends_effectchange_to_c197():
    dev = FakeHid({spectrum.OP_GET_BRIGHTNESS: bytes([0x07, 0, 0, 0, 5])})
    lights = Lights(_fs(), opener=lambda p: dev)
    lights.color((0, 0, 255))
    assert any(s[1] == 0xCB for s in dev.sent)      # EffectChange actually sent
    # and it carries real keycodes (num_keys byte after the single color is large)
    eff = next(s for s in dev.sent if s[1] == 0xCB)
    assert eff[25] == len(spectrum.KEYBOARD_KEYS)    # not 1 (the old 0x65-only bug)


def test_c193_with_marker_is_allowed_as_fallback():
    fs = FakeSysfs(
        {"/sys/class/hidraw/hidraw2/device/uevent": _uevent("048D", "C193")},
        binary={"/sys/class/hidraw/hidraw2/device/report_descriptor": _FF89},
    )
    assert Lights(fs, opener=lambda p: FakeHid()).candidates() == ["/dev/hidraw2"]


def test_no_effect_device_raises():
    fs = FakeSysfs(
        {"/sys/class/hidraw/hidraw2/device/uevent": _uevent("048D", "C193")},
        binary={"/sys/class/hidraw/hidraw2/device/report_descriptor": _NO_FF89},
    )
    lights = Lights(fs, opener=lambda p: FakeHid())
    assert lights.candidates() == []
    with pytest.raises(RuntimeError):
        lights.connect()
