from __future__ import annotations

import collections
import time
from typing import Callable

from ..hw.sensors import Sensors


class Monitor:
    """Samples sensors into a rolling history; computes CPU package watts from RAPL deltas."""

    def __init__(self, sensors: Sensors, maxlen: int = 120, clock: Callable[[], float] | None = None):
        self.sensors = sensors
        self.clock = clock or time.monotonic
        self.history: collections.deque[dict] = collections.deque(maxlen=maxlen)
        self._last_e: int | None = None
        self._last_t: float | None = None

    def sample(self) -> dict:
        now = self.clock()
        energy = self.sensors.rapl_energy_uj()
        power = None
        if energy is not None and self._last_e is not None and self._last_t is not None:
            power = Sensors.rapl_power_w(self._last_e, energy, now - self._last_t)
        self._last_e, self._last_t = energy, now

        snap = {
            "cpu_power_w": round(power, 1) if power is not None else None,
            "cpu_temp_c": self.sensors.cpu_package_temp_c(),
            "nvme_temps_c": self.sensors.nvme_temps_c(),
            "battery": self.sensors.battery(),
            "ac_online": self.sensors.ac_online(),
            "cpu_freq_mhz": self.sensors.cpu_freq_mhz(),
        }
        self.history.append(snap)
        return snap

    def latest(self) -> dict | None:
        return self.history[-1] if self.history else None
