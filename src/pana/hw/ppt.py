from __future__ import annotations

from .detect import PPT_DIR
from .transport import Sysfs


def _cur(attr: str) -> str:
    return f"{PPT_DIR}/{attr}/current_value"


def _min(attr: str) -> str:
    return f"{PPT_DIR}/{attr}/min_value"


def _max(attr: str) -> str:
    return f"{PPT_DIR}/{attr}/max_value"


class Ppt:
    """CPU power-limit tunables (firmware-attributes lenovo-wmi-other).

    NOTE on coupling: these only take effect when platform_profile == 'custom'.
    Sequencing (set custom first) is the caller's responsibility (see core.manager);
    this class only clamps and writes the raw attribute, and refuses attributes
    that have no bounds on this machine (e.g. ppt_pl3_fppt).
    """

    def __init__(self, fs: Sysfs):
        self.fs = fs

    def attrs(self) -> list[str]:
        return [p.split("/")[-2] for p in self.fs.glob(f"{PPT_DIR}/ppt_*/current_value")]

    def _read_int_or_none(self, path: str) -> int | None:
        if not self.fs.exists(path):
            return None
        raw = self.fs.read(path).strip()
        return int(raw) if raw else None

    def bounds(self, attr: str) -> tuple[int | None, int | None]:
        return self._read_int_or_none(_min(attr)), self._read_int_or_none(_max(attr))

    def settable(self, attr: str) -> bool:
        lo, hi = self.bounds(attr)
        return lo is not None and hi is not None

    def get(self, attr: str) -> int:
        return int(self.fs.read(_cur(attr)))

    def set(self, attr: str, value: int) -> int:
        """Clamp value to [min, max] and write it. Returns the clamped value."""
        lo, hi = self.bounds(attr)
        if lo is None or hi is None:
            raise ValueError(f"{attr} has no min/max bounds; not settable on this machine")
        clamped = max(lo, min(hi, value))
        self.fs.write(_cur(attr), str(clamped))
        return clamped
