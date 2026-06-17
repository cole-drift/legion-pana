from pana.core.monitor import Monitor


class _FakeSensors:
    def __init__(self, energies, wrap=None):
        self._energies = list(energies)
        self._i = -1
        self._wrap = wrap

    def rapl_energy_uj(self):
        self._i += 1
        return self._energies[self._i]

    def rapl_max_range_uj(self):
        return self._wrap

    def cpu_package_temp_c(self):
        return 52.0

    def nvme_temps_c(self):
        return [41.0]

    def battery(self):
        return {"capacity": 38, "status": "Charging", "power_w": 15.0}

    def ac_online(self):
        return True

    def cpu_freq_mhz(self):
        return {"avg": 3000.0, "max": 4000.0}


def test_first_sample_has_no_power_second_computes():
    # energies 1s apart (clock advances 1.0 each call), 10 J delta -> 10 W
    clock_vals = iter([100.0, 101.0])
    mon = Monitor(_FakeSensors([1_000_000, 11_000_000]), clock=lambda: next(clock_vals))

    first = mon.sample()
    assert first["cpu_power_w"] is None
    assert first["cpu_temp_c"] == 52.0

    second = mon.sample()
    assert second["cpu_power_w"] == 10.0


def test_counter_wrap_yields_positive_power():
    # second energy reading is below the first (counter rolled over); with the
    # max-range known, power must come out positive, not negative.
    wrap = 10_000_000
    clock_vals = iter([0.0, 1.0])
    sensors = _FakeSensors([9_500_000, 1_000_000], wrap=wrap)
    mon = Monitor(sensors, clock=lambda: next(clock_vals))
    mon.sample()  # primes last_e
    second = mon.sample()
    assert second["cpu_power_w"] == 1.5  # (1_000_000 - 9_500_000 + 10_000_000)/1e6 / 1s


def test_history_bounded():
    mon = Monitor(_FakeSensors([0] * 5), maxlen=2, clock=lambda: 0.0)
    for _ in range(5):
        mon.sample()
    assert len(mon.history) == 2
    assert mon.latest() is not None
