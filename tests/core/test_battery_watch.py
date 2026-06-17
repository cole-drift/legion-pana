from pana.core.battery_watch import BatteryWatcher, decide


def test_decide_no_target():
    assert decide(50, None, False) is None


def test_decide_enables_cap_at_target():
    assert decide(85, 85, False) is True       # reached target, not yet capped -> enable
    assert decide(85, 85, True) is None         # already capped -> no change


def test_decide_disables_below_hysteresis():
    assert decide(82, 85, True, hysteresis=3) is False  # dropped to target-hyst -> allow charge
    assert decide(82, 85, False, hysteresis=3) is None  # already charging -> no change


def test_decide_in_deadband():
    assert decide(83, 85, True, hysteresis=3) is None
    assert decide(83, 85, False, hysteresis=3) is None


def test_decide_missing_capacity():
    assert decide(None, 85, False) is None


class _FakeBattery:
    def __init__(self, capacity, conservation):
        self._cap = capacity
        self._cons = conservation
        self.toggles: list[bool] = []

    def capacity(self):
        return self._cap

    def conservation(self):
        return self._cons

    def set_conservation(self, on):
        self._cons = on
        self.toggles.append(on)


def test_watcher_tick_enables():
    bat = _FakeBattery(capacity=85, conservation=False)
    w = BatteryWatcher(bat, get_target=lambda: 85)
    assert w.tick() is True
    assert bat.toggles == [True]


def test_watcher_tick_noop_when_no_target():
    bat = _FakeBattery(capacity=85, conservation=False)
    w = BatteryWatcher(bat, get_target=lambda: None)
    assert w.tick() is None
    assert bat.toggles == []
