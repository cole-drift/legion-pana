from __future__ import annotations

from .battery import AC_ONLINE, CAPACITY, POWER_NOW, STATUS
from .transport import Sysfs

HWMON_GLOB = "/sys/class/hwmon/hwmon*"
RAPL_ENERGY = "/sys/class/powercap/intel-rapl:0/energy_uj"
RAPL_MAX_RANGE = "/sys/class/powercap/intel-rapl:0/max_energy_range_uj"
CPUFREQ_GLOB = "/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"


class Sensors:
    """Read-only telemetry: temps, CPU package power (RAPL), battery, cpufreq.

    Every read is resilient: an unreadable sensor (e.g. RAPL energy_uj is
    root-only on modern kernels) yields None for that field rather than
    blanking the whole sample.
    """

    def __init__(self, fs: Sysfs):
        self.fs = fs

    def _read(self, path: str) -> str | None:
        try:
            return self.fs.read(path)
        except OSError:
            return None

    def _read_int(self, path: str) -> int | None:
        v = self._read(path)
        if v is None or v == "":
            return None
        try:
            return int(v)
        except ValueError:
            return None

    def _hwmon_dir(self, name: str) -> str | None:
        for d in self.fs.glob(f"{HWMON_GLOB}/name"):
            if self._read(d) == name:
                return d.rsplit("/", 1)[0]
        return None

    def _labeled_temp_c(self, hwmon: str, label: str) -> float | None:
        for lbl in self.fs.glob(f"{hwmon}/temp*_label"):
            if self._read(lbl) == label:
                mC = self._read_int(lbl.replace("_label", "_input"))
                return mC / 1000.0 if mC is not None else None
        return None

    def cpu_package_temp_c(self) -> float | None:
        hwmon = self._hwmon_dir("coretemp")
        return self._labeled_temp_c(hwmon, "Package id 0") if hwmon else None

    def nvme_temps_c(self) -> list[float]:
        temps: list[float] = []
        for name in self.fs.glob(f"{HWMON_GLOB}/name"):
            if self._read(name) != "nvme":
                continue
            hwmon = name.rsplit("/", 1)[0]
            for inp in self.fs.glob(f"{hwmon}/temp*_input"):
                mC = self._read_int(inp)
                if mC is not None:
                    temps.append(mC / 1000.0)
        return temps

    def rapl_energy_uj(self) -> int | None:
        return self._read_int(RAPL_ENERGY)

    @staticmethod
    def rapl_power_w(e0_uj: int, e1_uj: int, dt_s: float, wrap_uj: int | None = None) -> float:
        delta = e1_uj - e0_uj
        if delta < 0 and wrap_uj:
            delta += wrap_uj
        if dt_s <= 0:
            return 0.0
        return (delta / 1_000_000.0) / dt_s

    def battery(self) -> dict:
        power_uw = self._read_int(POWER_NOW)
        return {
            "capacity": self._read_int(CAPACITY),
            "status": self._read(STATUS),
            "power_w": (power_uw / 1_000_000.0) if power_uw is not None else None,
        }

    def ac_online(self) -> bool | None:
        v = self._read(AC_ONLINE)
        return (v == "1") if v is not None else None

    def cpu_freq_mhz(self) -> dict:
        freqs = [k / 1000.0 for k in (self._read_int(p) for p in self.fs.glob(CPUFREQ_GLOB)) if k is not None]
        if not freqs:
            return {"avg": None, "max": None}
        return {"avg": round(sum(freqs) / len(freqs), 1), "max": round(max(freqs), 1)}
