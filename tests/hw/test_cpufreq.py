from pana.hw.cpufreq import MAX_PERF_PCT, CpuFreq
from pana.hw.transport import FakeSysfs


def _fs(pct="100"):
    return FakeSysfs({MAX_PERF_PCT: pct})


def test_available_and_get():
    c = CpuFreq(_fs("100"))
    assert c.available() is True
    assert c.get_max_pct() == 100


def test_set_writes_value():
    fs = _fs()
    assert CpuFreq(fs).set_max_pct(55) == 55
    assert fs.read(MAX_PERF_PCT) == "55"


def test_set_clamps_high_and_low():
    fs = _fs()
    assert CpuFreq(fs).set_max_pct(250) == 100
    assert CpuFreq(fs).set_max_pct(0) == 10  # FLOOR_PCT


def test_unavailable():
    c = CpuFreq(FakeSysfs({}))
    assert c.available() is False
    assert c.get_max_pct() is None
