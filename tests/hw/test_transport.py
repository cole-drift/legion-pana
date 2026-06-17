import pytest
from pana.hw.transport import FakeSysfs


def test_read_strips_whitespace():
    fs = FakeSysfs({"/sys/x": "performance\n"})
    assert fs.read("/sys/x") == "performance"


def test_read_missing_raises():
    fs = FakeSysfs({})
    with pytest.raises(FileNotFoundError):
        fs.read("/sys/nope")


def test_write_records_and_updates():
    fs = FakeSysfs({"/sys/x": "0"})
    fs.write("/sys/x", "1")
    assert fs.read("/sys/x") == "1"
    assert fs.writes == [("/sys/x", "1")]


def test_write_missing_raises():
    fs = FakeSysfs({})
    with pytest.raises(FileNotFoundError):
        fs.write("/sys/nope", "1")


def test_exists():
    fs = FakeSysfs({"/sys/x": "1"})
    assert fs.exists("/sys/x") is True
    assert fs.exists("/sys/y") is False


def test_glob_matches_sorted():
    fs = FakeSysfs({
        "/a/ppt_pl1_spl/current_value": "70",
        "/a/ppt_pl2_sppt/current_value": "125",
        "/a/ppt_pl1_spl/min_value": "50",
    })
    assert fs.glob("/a/ppt_*/current_value") == [
        "/a/ppt_pl1_spl/current_value",
        "/a/ppt_pl2_sppt/current_value",
    ]
