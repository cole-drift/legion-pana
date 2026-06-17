import pytest

from pana.hw import detect as d
from pana.hw.ppt import Ppt
from pana.hw.transport import FakeSysfs


def _fs() -> FakeSysfs:
    return FakeSysfs({
        f"{d.PPT_DIR}/ppt_pl1_spl/current_value": "0",
        f"{d.PPT_DIR}/ppt_pl1_spl/min_value": "50",
        f"{d.PPT_DIR}/ppt_pl1_spl/max_value": "110",
        f"{d.PPT_DIR}/ppt_pl2_sppt/current_value": "0",
        f"{d.PPT_DIR}/ppt_pl2_sppt/min_value": "60",
        f"{d.PPT_DIR}/ppt_pl2_sppt/max_value": "168",
        # pl3 has empty bounds on this machine — not settable
        f"{d.PPT_DIR}/ppt_pl3_fppt/current_value": "0",
        f"{d.PPT_DIR}/ppt_pl3_fppt/min_value": "",
        f"{d.PPT_DIR}/ppt_pl3_fppt/max_value": "",
    })


def test_attrs_discovered():
    assert Ppt(_fs()).attrs() == ["ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"]


def test_bounds_and_settable():
    ppt = Ppt(_fs())
    assert ppt.bounds("ppt_pl1_spl") == (50, 110)
    assert ppt.settable("ppt_pl1_spl") is True
    assert ppt.settable("ppt_pl3_fppt") is False


def test_set_clamps_high():
    fs = _fs()
    assert Ppt(fs).set("ppt_pl1_spl", 999) == 110
    assert fs.read(f"{d.PPT_DIR}/ppt_pl1_spl/current_value") == "110"


def test_set_clamps_low():
    fs = _fs()
    assert Ppt(fs).set("ppt_pl1_spl", 10) == 50


def test_set_within_range():
    fs = _fs()
    assert Ppt(fs).set("ppt_pl2_sppt", 90) == 90


def test_set_unbounded_attr_raises():
    fs = _fs()
    with pytest.raises(ValueError):
        Ppt(fs).set("ppt_pl3_fppt", 100)
    assert fs.writes == []
