import pytest

from pana.hw import detect as d
from pana.hw.platform_profile import PlatformProfile
from pana.hw.transport import FakeSysfs


def _fs() -> FakeSysfs:
    return FakeSysfs({
        d.PLATFORM_PROFILE: "performance",
        d.PLATFORM_PROFILE_CHOICES: "low-power balanced balanced-performance performance custom",
    })


def test_get_and_choices():
    pp = PlatformProfile(_fs())
    assert pp.available() is True
    assert pp.get() == "performance"
    assert "custom" in pp.choices()


def test_set_valid_writes():
    fs = _fs()
    PlatformProfile(fs).set("low-power")
    assert fs.read(d.PLATFORM_PROFILE) == "low-power"
    assert fs.writes == [(d.PLATFORM_PROFILE, "low-power")]


def test_set_invalid_raises_and_does_not_write():
    fs = _fs()
    with pytest.raises(ValueError):
        PlatformProfile(fs).set("turbo")
    assert fs.writes == []


def test_unavailable_machine():
    pp = PlatformProfile(FakeSysfs({}))
    assert pp.available() is False
    assert pp.choices() == []
