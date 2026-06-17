from __future__ import annotations

from typing import Callable

from ..hw.battery import Battery
from ..hw.cpufreq import CpuFreq
from ..hw.hid import HidTransport, RealHid
from ..hw.lights import Lights
from ..hw.platform_profile import PlatformProfile
from ..hw.sensors import Sensors
from ..hw.transport import RealSysfs, Sysfs
from .config import Config, State
from .presets import Preset, default_presets


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
        self.cpufreq = CpuFreq(self.fs)
        self.battery = Battery(self.fs)
        self.sensors = Sensors(self.fs)
        self.lights = Lights(self.fs, lights_opener or (lambda path: RealHid(path)))
        self.config = config or Config()
        self.state = state or State()
        self.presets = presets or default_presets()
        # clock-ceiling cap we want held (against thermald raising it); None = don't enforce.
        self._desired_pct: int | None = None
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
        # platform_profile is cosmetic on this firmware (sets the power-button color
        # but does NOT change power limits), so a hiccup here must not block the cap.
        _safe(lambda: self.profile.set(p.platform_profile))
        # the actual cooling lever: intel_pstate clock-ceiling cap.
        if self.cpufreq.available():
            if p.eco_cap:
                pct = self.config.eco_max_perf_pct
                self.cpufreq.set_max_pct(pct)
                self._desired_pct = pct
            else:
                self.cpufreq.set_max_pct(100)
                self._desired_pct = None  # uncapped: don't enforce
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

    def set_power(self, pct: int) -> dict:
        """Set a custom CPU clock-ceiling cap (intel_pstate max_perf_pct, 10-100)."""
        if not self.cpufreq.available():
            raise RuntimeError("CPU clock cap not available on this machine")
        applied = self.cpufreq.set_max_pct(pct)
        self._desired_pct = applied if applied < 100 else None
        self.state.mode = "custom"
        self.state.custom_max_pct = applied
        self._persist()
        return self.status()

    def enforce_cap(self) -> None:
        """Re-assert an active clock cap if something raised the ceiling back up.

        Only pushes the ceiling DOWN to the desired cap — never fights thermald when it
        lowers the ceiling for thermal safety.
        """
        if self._desired_pct is None or not self.cpufreq.available():
            return
        cur = self.cpufreq.get_max_pct()
        if cur is not None and cur > self._desired_pct:
            _safe(lambda: self.cpufreq.set_max_pct(self._desired_pct))

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
        if on is True:
            # an explicit brightness on this invocation wins over the config default
            self.lights.set_brightness(
                brightness if brightness is not None else self.config.light_on_brightness
            )
            self.state.lights_manual = "on"
        elif on is False:
            self.lights.off()
            self.state.lights_manual = "off"
        elif brightness is not None:
            self.lights.set_brightness(brightness)
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
        if self.state.mode == "custom":
            if self.cpufreq.available() and self.state.custom_max_pct:
                applied = _safe(lambda: self.cpufreq.set_max_pct(self.state.custom_max_pct))
                self._desired_pct = applied if applied and applied < 100 else None
        elif self.state.mode:
            _safe(lambda: self._apply_preset(self.presets[self.state.mode]))

    # ---- read-only status ----

    def status(self) -> dict:
        return {
            "mode": self.state.mode,
            "platform_profile": _safe(self.profile.get) if self.profile.available() else None,
            "profile_choices": self.profile.choices(),
            "cpu_cap": {
                "available": self.cpufreq.available(),
                "max_perf_pct": self.cpufreq.get_max_pct() if self.cpufreq.available() else None,
                "desired_pct": self._desired_pct,
            },
            "battery": {
                "conservation": self.battery.conservation(),
                "soft_target": self.state.battery_target,
                "capacity": self.battery.capacity(),
                "status": self.battery.status(),
                "ac_online": self.battery.ac_online(),
                # honesty disclosure (spec §4): the soft target is software-enforced
                # and cannot brake below the firmware conservation cap (~60-80%).
                "reverts_to_charging_if_daemon_stops": True,
                "firmware_cap_floor": True,
                "soft_target_note": (
                    "held in software; reverts to charging if the daemon stops; "
                    "cannot hold below the firmware conservation cap (~60-80%)"
                )
                if self.state.battery_target is not None
                else None,
            },
            "lights": {
                "available": self.lights.available(),
                "manual": self.state.lights_manual,
                "night_enabled": self.night_enabled(),
            },
        }
