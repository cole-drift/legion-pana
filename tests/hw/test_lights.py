import pytest

from pana.hw import spectrum
from pana.hw.hid import FakeHid
from pana.hw.lights import Lights
from pana.hw.transport import FakeSysfs


def _uevent(vid: str, pid: str) -> str:
    return f"HID_ID=0003:0000{vid}:0000{pid}\nHID_NAME=Lenovo Lighting\n"


def _fs() -> FakeSysfs:
    return FakeSysfs({
        "/sys/class/hidraw/hidraw2/device/uevent": _uevent("048D", "C193"),
        "/sys/class/hidraw/hidraw4/device/uevent": _uevent("048D", "C197"),
        "/sys/class/hidraw/hidraw0/device/uevent": _uevent("1234", "5678"),  # unrelated
    })


def test_candidates_filters_by_vid_pid():
    lights = Lights(_fs(), opener=lambda p: FakeHid())
    assert lights.candidates() == ["/dev/hidraw2", "/dev/hidraw4"]


def test_connect_picks_responsive_device():
    # c193 (hidraw2) answers with junk brightness 200; c197 (hidraw4) answers 5.
    bad = FakeHid({spectrum.OP_GET_BRIGHTNESS: bytes([0x07, 0, 0, 0, 200])})
    good = FakeHid({spectrum.OP_GET_BRIGHTNESS: bytes([0x07, 0, 0, 0, 5])})
    devs = {"/dev/hidraw2": bad, "/dev/hidraw4": good}
    lights = Lights(_fs(), opener=lambda p: devs[p])
    assert lights.connect() == "/dev/hidraw4"


def test_off_sends_brightness_zero():
    good = FakeHid({spectrum.OP_GET_BRIGHTNESS: bytes([0x07, 0, 0, 0, 5])})
    lights = Lights(_fs(), opener=lambda p: good if p == "/dev/hidraw4" else FakeHid(
        {spectrum.OP_GET_BRIGHTNESS: bytes([0x07, 0, 0, 0, 200])}
    ))
    lights.off()
    # last sent report is set-brightness level 0
    assert good.sent[-1][:5] == bytes([0x07, 0xCE, 0xC0, 0x03, 0])


def test_no_device_raises():
    lights = Lights(FakeSysfs({}), opener=lambda p: FakeHid())
    with pytest.raises(RuntimeError):
        lights.connect()
