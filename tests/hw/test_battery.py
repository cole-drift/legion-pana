from pana.hw import detect as d
from pana.hw.battery import AC_ONLINE, CAPACITY, STATUS, Battery
from pana.hw.transport import FakeSysfs


def test_conservation_via_ideapad():
    fs = FakeSysfs({d.CONSERVATION: "0"})
    b = Battery(fs)
    assert b.available() is True
    assert b.conservation() is False
    b.set_conservation(True)
    assert fs.read(d.CONSERVATION) == "1"
    assert b.conservation() is True


def test_conservation_via_charge_types_fallback():
    fs = FakeSysfs({d.CHARGE_TYPES: "[Standard] Long_Life"})
    b = Battery(fs)
    assert b.conservation() is False  # Standard is active
    b.set_conservation(True)
    assert fs.read(d.CHARGE_TYPES) == "Long_Life"


def test_prefers_conservation_node_when_both_present():
    fs = FakeSysfs({d.CONSERVATION: "0", d.CHARGE_TYPES: "[Standard] Long_Life"})
    Battery(fs).set_conservation(True)
    assert fs.read(d.CONSERVATION) == "1"
    assert fs.read(d.CHARGE_TYPES) == "[Standard] Long_Life"  # untouched


def test_state_reads():
    fs = FakeSysfs({CAPACITY: "38", STATUS: "Charging", AC_ONLINE: "1"})
    b = Battery(fs)
    assert b.capacity() == 38
    assert b.status() == "Charging"
    assert b.ac_online() is True


def test_unavailable():
    b = Battery(FakeSysfs({}))
    assert b.available() is False
    assert b.conservation() is None
