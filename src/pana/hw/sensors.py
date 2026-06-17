from __future__ import annotations

from .battery import AC_ONLINE, CAPACITY, POWER_NOW, STATUS
from .transport import Sysfs

HWMON_GLOB = "/sys/class/hwmon/hwmon*"
RAPL_ENERGY = "/sys/class/powercap/intel-rapl:0/energy_uj"
RAPL_MAX_RANGE = "/sys/class/powercap/intel-rapl:0/max_energy_range_uj"
CPUFREQ_GLOB = "/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"


class Sensors:
    """Read-only telemetry: temps, CPU package power (RAPL), battery, cpufreq."""

    def __init__(self, fs: Sysfs):
        self.fs = fs

    def _hwmon_dir(self, name: str) -> str | None:
        for d in self.fs.glob(f"{HWMON_GLOB}/name"):
            if self.fs.read(d) == name:
                return d.rsplit("/", 1)[0]
        return None

    def _labeled_temp_c(self, hwmon: str, label: str) -> float | None:
        for lbl in self.fs.glob(f"{hwmon}/temp*_label"):
            if self.fs.read(lbl) == label:
                inp = lbl.replace("_label", "_input")
                if self.fs.exists(inp):
                    return int(self.fs.read(inp)) / 1000.0
        return None

    def cpu_package_temp_c(self) -> float | None:
        hwmon = self._hwmon_dir("coretemp")
        if hwmon is None:
            return None
        return self._labeled_temp_c(hwmon, "Package id 0")

    def nvme_temps_c(self) -> list[float]:
        temps: list[float] = []
        for name in self.fs.glob(f"{HWMON_GLOB}/name"):
            if self.fs.read(name) != "nvme":
                continue
            hwmon = name.rsplit("/", 1)[0]
            for inp in self.fs.glob(f"{hwmon}/temp*_input"):
                temps.append(int(self.fs.read(inp)) / 1000.0)
        return temps

    def rapl_energy_uj(self) -> int | None:
        return int(self.fs.read(RAPL_ENERGY)) if self.fs.exists(RAPL_ENERGY) else None

    @staticmethod
    def rapl_power_w(e0_uj: int, e1_uj: int, dt_s: float, wrap_uj: int | None = None) -> float:
        """CPU package watts from two RAPL energy_uj samples and the interval.

        Handles the counter wrapping at max_energy_range_uj when wrap_uj is given.
        """
        delta = e1_uj - e0_uj
        if delta < 0 and wrap_uj:
            delta += wrap_uj
        if dt_s <= 0:
            return 0.0
        return (delta / 1_000_000.0) / dt_s

    def battery(self) -> dict:
        def _int(path: str) -> int | None:
            return int(self.fs.read(path)) if self.fs.exists(path) else None

        power_uw = _int(POWER_NOW)
        return {
            "capacity": _int(CAPACITY),
            "status": self.fs.read(STATUS) if self.fs.exists(STATUS) else None,
            "power_w": (power_uw / 1_000_000.0) if power_uw is not None else None,
        }

    def ac_online(self) -> bool | None:
        return self.fs.read(AC_ONLINE) == "1" if self.fs.exists(AC_ONLINE) else None

    def cpu_freq_mhz(self) -> dict:
        freqs = [int(self.fs.read(p)) / 1000.0 for p in self.fs.glob(CPUFREQ_GLOB)]
        if not freqs:
            return {"avg": None, "max": None}
        return {"avg": round(sum(freqs) / len(freqs), 1), "max": round(max(freqs), 1)}
