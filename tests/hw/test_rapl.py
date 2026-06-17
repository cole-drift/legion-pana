from pana.hw.rapl import PL1, PL1_MAX, PL2, Rapl
from pana.hw.transport import FakeSysfs


def _fs() -> FakeSysfs:
    return FakeSysfs({
        "/sys/class/powercap/intel-rapl:0/name": "package-0",
        PL1: "115000000",
        PL2: "168000000",
        PL1_MAX: "120000000",
    })


def test_available_and_read():
    r = Rapl(_fs())
    assert r.available() is True
    assert r.name() == "package-0"
    assert r.get_limits_w() == {"pl1": 115.0, "pl2": 168.0}


def test_set_pl1_writes_microwatts():
    fs = _fs()
    assert Rapl(fs).set_pl1_w(45) == 45.0
    assert fs.read(PL1) == "45000000"


def test_set_pl1_clamps_to_max_power():
    fs = _fs()
    # max_power is 120W -> request 999 clamps to 120
    assert Rapl(fs).set_pl1_w(999) == 120.0


def test_set_clamps_to_floor():
    fs = _fs()
    assert Rapl(fs).set_pl1_w(1) == 8.0  # FLOOR_W


def test_set_pl2_uses_hard_max_when_no_max_file():
    fs = _fs()  # no PL2_MAX present
    assert Rapl(fs).set_pl2_w(9999) == 224.0  # HARD_MAX_W


def test_unavailable():
    assert Rapl(FakeSysfs({})).available() is False
