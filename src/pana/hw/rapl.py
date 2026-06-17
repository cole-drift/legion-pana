from __future__ import annotations

from .transport import Sysfs

RAPL = "/sys/class/powercap/intel-rapl:0"
NAME = f"{RAPL}/name"
PL1 = f"{RAPL}/constraint_0_power_limit_uw"
PL2 = f"{RAPL}/constraint_1_power_limit_uw"
PL1_MAX = f"{RAPL}/constraint_0_max_power_uw"
PL2_MAX = f"{RAPL}/constraint_1_max_power_uw"

FLOOR_W = 8.0       # never cap below this (machine would be unusably slow / unstable)
HARD_MAX_W = 224.0  # safety ceiling if no max_power_uw is exposed


class Rapl:
    """Intel RAPL package power-cap (constraint_0 = PL1 sustained, constraint_1 = PL2 boost).

    This is the standard Linux power-cap and is the lever that actually works on
    this machine — the Lenovo platform_profile/ppt path does not change the limits.
    """

    def __init__(self, fs: Sysfs):
        self.fs = fs

    def available(self) -> bool:
        return self.fs.exists(PL1)

    def name(self) -> str | None:
        return self.fs.read(NAME) if self.fs.exists(NAME) else None

    def _read_w(self, path: str) -> float | None:
        if not self.fs.exists(path):
            return None
        raw = self.fs.read(path).strip()
        if not raw:
            return None
        try:
            return int(raw) / 1_000_000
        except ValueError:
            return None

    def get_limits_w(self) -> dict:
        return {"pl1": self._read_w(PL1), "pl2": self._read_w(PL2)}

    def _set(self, path: str, max_path: str, watts: float) -> float:
        hi = self._read_w(max_path) or HARD_MAX_W
        clamped = max(FLOOR_W, min(hi, float(watts)))
        self.fs.write(path, str(int(clamped * 1_000_000)))
        return clamped

    def set_pl1_w(self, watts: float) -> float:
        return self._set(PL1, PL1_MAX, watts)

    def set_pl2_w(self, watts: float) -> float:
        return self._set(PL2, PL2_MAX, watts)
