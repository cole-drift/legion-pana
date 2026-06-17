from __future__ import annotations

from .transport import Sysfs

# intel_pstate global max performance clamp (1-100). This is an OS-level P-state
# ceiling — unlike RAPL power limits it is NOT a firmware MSR, so it is not BIOS-locked.
MAX_PERF_PCT = "/sys/devices/system/cpu/intel_pstate/max_perf_pct"
STATUS = "/sys/devices/system/cpu/intel_pstate/status"

FLOOR_PCT = 10  # never clamp below this (machine would be painfully slow)


class CpuFreq:
    """Cooling lever via intel_pstate max_perf_pct (the one writable on this machine).

    Lowering the percentage caps the CPU clock ceiling -> less heat and power draw.
    """

    def __init__(self, fs: Sysfs):
        self.fs = fs

    def available(self) -> bool:
        return self.fs.exists(MAX_PERF_PCT)

    def get_max_pct(self) -> int | None:
        if not self.fs.exists(MAX_PERF_PCT):
            return None
        raw = self.fs.read(MAX_PERF_PCT).strip()
        try:
            return int(raw)
        except ValueError:
            return None

    def set_max_pct(self, pct: int) -> int:
        clamped = max(FLOOR_PCT, min(100, int(pct)))
        self.fs.write(MAX_PERF_PCT, str(clamped))
        return clamped
