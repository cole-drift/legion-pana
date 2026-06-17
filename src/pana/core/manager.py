from __future__ import annotations

from typing import Callable

from ..hw.battery import Battery
from ..hw.hid import HidTransport, RealHid
from ..hw.lights import Lights
from ..hw.platform_profile import PlatformProfile
from ..hw.ppt import Ppt
from ..hw.sensors import Sensors
from ..hw.transport import RealSysfs, Sysfs
from .config import Config, State
from .presets import Preset, custom_tdp_preset, default_presets


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


class Manager:
    """Owns the hardware controllers and implements high-level operations.

    All business logic lives here; the daemon just maps IPC commands to these
    methods. Fully testable with a FakeSysfs and a fake lights opener.
    """

    def __init__(
        self,
        fs: Sysfs | None = None,
        lights_opener: Callable[[str], HidTransport] | None = None,
        config: Config | None = None,
        state: State | None = None,
        presets: dict[str, Preset] | None = None,
    ):
        self.fs = fs or RealSysfs()
        self.profile = PlatformProfile(self.fs)
        self.ppt = Ppt(self.fs)
        self.battery = Battery(self.fs)
        self.sensors = Sensors(self.fs)
        self.lights = Lights(self.fs, lights_opener or (lambda path: RealHid(path)))
        self.config = config or Config()
        self.state = state or State()
        self.presets = presets or default_presets()
        if self.state.battery_target is None:
            self.state.battery_target = self.config.battery_target
        if self.state.mode is None:
            self.state.mode = self.config.default_mode

    # ---- effective settings ----

    def night_enabled(self) -> bool:
        if self.state.night_enabled is not None:
            return self.state.night_enabled
        return self.config.night_enabled

    # ---- internal apply ----

    def _apply_preset(self, p: Preset) -> None:
        if p.ppt:
            self.profile.set("custom")
            for attr, watts in p.ppt.items():
                self.ppt.set(attr, watts)
        else:
            self.profile.set(p.platform_profile)
        if p.battery == "cap":
            self.battery.set_conservation(True)
        elif p.battery == "off":
            self.battery.set_conservation(False)
        if self.lights.available():
            if p.lights == "off":
                self.lights.off()
            elif p.lights == "on":
                self.lights.set_brightness(self.config.light_on_brightness)

    def _persist(self) -> None:
        _safe(self.state.save)

    # ---- operations ----

    def apply_mode(self, name: str) -> dict:
        p = self.presets.get(name)
        if p is None:
            raise ValueError(f"unknown mode: {name}")
        self._apply_preset(p)
        self.state.mode = name
        self._persist()
        return self.status()

    def set_tdp(self, pl1: int | None = None, pl2: int | None = None) -> dict:
        if pl1 is None and pl2 is None:
            raise ValueError("set_tdp needs at least one of pl1, pl2")
        self._apply_preset(custom_tdp_preset(pl1, pl2))
        self.state.mode = "custom"
        self._persist()
        return self.status()

    def set_battery(
        self, *, cap: bool = False, target: int | None = None, off: bool = False
    ) -> dict:
        if off:
            self.battery.set_conservation(False)
            self.state.battery_target = None
        elif cap:
            self.battery.set_conservation(True)
            self.state.battery_target = None
        elif target is not None:
            self.state.battery_target = int(target)
            cur = self.battery.capacity()
            if cur is not None and cur >= target:
                self.battery.set_conservation(True)
        self._persist()
        return self.status()

    def set_lights(
        self,
        *,
        on: bool | None = None,
        brightness: int | None = None,
        color: tuple[int, int, int] | None = None,
    ) -> dict:
        if not self.lights.available():
            raise RuntimeError("no lighting device available")
        if color is not None:
            self.lights.color(color)
        if brightness is not None:
            self.lights.set_brightness(brightness)
        if on is True:
            self.lights.set_brightness(self.config.light_on_brightness)
            self.state.lights_manual = "on"
        elif on is False:
            self.lights.off()
            self.state.lights_manual = "off"
        self._persist()
        return self.status()

    def set_night(self, enabled: bool | None = None, clear_manual: bool = False) -> dict:
        if enabled is not None:
            self.state.night_enabled = enabled
        if clear_manual:
            self.state.lights_manual = None
        self._persist()
        return self.status()

    def reapply(self) -> None:
        """Re-apply persisted desired state (boot / resume / AC change)."""
        if self.state.mode and self.state.mode != "custom":
            _safe(lambda: self._apply_preset(self.presets[self.state.mode]))

    # ---- read-only status ----

    def status(self) -> dict:
        return {
            "mode": self.state.mode,
            "platform_profile": _safe(self.profile.get) if self.profile.available() else None,
            "profile_choices": self.profile.choices(),
            "ppt": {a: _safe(lambda a=a: self.ppt.get(a)) for a in self.ppt.attrs()},
            "battery": {
                "conservation": self.battery.conservation(),
                "soft_target": self.state.battery_target,
                "capacity": self.battery.capacity(),
                "status": self.battery.status(),
                "ac_online": self.battery.ac_online(),
            },
            "lights": {
                "available": self.lights.available(),
                "manual": self.state.lights_manual,
                "night_enabled": self.night_enabled(),
            },
        }
