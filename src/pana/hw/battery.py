from __future__ import annotations

from .detect import CHARGE_TYPES, CONSERVATION
from .transport import Sysfs

CAPACITY = "/sys/class/power_supply/BAT0/capacity"
STATUS = "/sys/class/power_supply/BAT0/status"
POWER_NOW = "/sys/class/power_supply/BAT0/power_now"  # microwatts
AC_ONLINE = "/sys/class/power_supply/ADP0/online"


class Battery:
    """Battery conservation (charge-cap) control + state reads.

    Two equivalent firmware levers exist; we prefer ideapad conservation_mode
    and fall back to the newer BAT0/charge_types enum. The cap percentage is
    firmware-fixed and NOT settable — arbitrary sub-cap targets are enforced in
    software by core.battery_watch, not here.
    """

    def __init__(self, fs: Sysfs):
        self.fs = fs

    def available(self) -> bool:
        return self.fs.exists(CONSERVATION) or self.fs.exists(CHARGE_TYPES)

    def conservation(self) -> bool | None:
        if self.fs.exists(CONSERVATION):
            return self.fs.read(CONSERVATION) == "1"
        if self.fs.exists(CHARGE_TYPES):
            return self._charge_types_active() == "Long_Life"
        return None

    def _charge_types_active(self) -> str | None:
        # charge_types reads like "[Standard] Long_Life"; the bracketed token is active.
        raw = self.fs.read(CHARGE_TYPES)
        for tok in raw.split():
            if tok.startswith("[") and tok.endswith("]"):
                return tok[1:-1]
        return None

    def set_conservation(self, on: bool) -> None:
        if self.fs.exists(CONSERVATION):
            self.fs.write(CONSERVATION, "1" if on else "0")
        elif self.fs.exists(CHARGE_TYPES):
            self.fs.write(CHARGE_TYPES, "Long_Life" if on else "Standard")
        else:
            raise RuntimeError("no battery conservation lever on this machine")

    def capacity(self) -> int | None:
        return int(self.fs.read(CAPACITY)) if self.fs.exists(CAPACITY) else None

    def status(self) -> str | None:
        return self.fs.read(STATUS) if self.fs.exists(STATUS) else None

    def ac_online(self) -> bool | None:
        return self.fs.read(AC_ONLINE) == "1" if self.fs.exists(AC_ONLINE) else None
