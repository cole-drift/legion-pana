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
from .presets import MODE_ALIASES, Preset, default_presets


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

    def night_window(self) -> tuple[str, str]:
        start = self.state.night_start or self.config.night_start
        end = self.state.night_end or self.config.night_end
        return start, end

    def _mode_pct(self, name: str) -> int:
        return {
            "eco": self.config.eco_pct,
            "balanced": self.config.balanced_pct,
            "performance": self.config.performance_pct,
        }.get(name, 100)

    # ---- internal apply ----

    def _apply_preset(self, p: Preset) -> None:
        # A mode = a CPU clock-ceiling tier + a cosmetic platform_profile (power-button
        # color). It does NOT touch battery or lights — those are controlled separately.
        _safe(lambda: self.profile.set(p.platform_profile))
        if self.cpufreq.available():
            pct = self._mode_pct(p.name)
            self.cpufreq.set_max_pct(pct)
            self._desired_pct = pct if pct < 100 else None  # only enforce a real cap

    def _persist(self) -> None:
        _safe(self.state.save)

    # ---- operations ----

    def apply_mode(self, name: str) -> dict:
        name = MODE_ALIASES.get(name, name)
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

    def _apply_appearance(self) -> None:
        """Re-send the saved effect/color (used when turning lights back on)."""
        eff, col = self.state.light_effect, self.state.light_color
        if eff == "rainbow":
            self.lights.rainbow()
        elif eff == "breathe" and col:
            self.lights.breathe(tuple(col))
        elif col:
            self.lights.color(tuple(col))

    def _lights_on(self) -> None:
        """Turn lights on, restoring the saved appearance + brightness."""
        self._apply_appearance()
        b = self.state.light_brightness or self.config.light_on_brightness
        self.lights.set_brightness(b)
        self.state.light_brightness, self.state.light_on = b, True

    def set_lights(
        self,
        *,
        on: bool | None = None,
        brightness: int | None = None,
        color: tuple[int, int, int] | None = None,
        effect: str | None = None,
        zone: str = "keyboard",
        logo: bool | None = None,
    ) -> dict:
        if not self.lights.available():
            raise RuntimeError("no lighting device available")

        if logo is not None:
            self.lights.logo(logo)

        # saved appearance is tracked for the keyboard zone only; other zones apply directly
        track = zone == "keyboard"
        appearance_changed = (effect is not None or color is not None) and track
        if effect == "rainbow":
            self.lights.rainbow(zone=zone)
            if track:
                self.state.light_effect, self.state.light_color = "rainbow", None
        elif effect == "breathe":
            rgb = tuple(color) if color else tuple(self.state.light_color or (255, 255, 255))
            self.lights.breathe(rgb, zone=zone)
            if track:
                self.state.light_effect, self.state.light_color = "breathe", list(rgb)
        elif color is not None or effect == "static":
            rgb = tuple(color) if color else tuple(self.state.light_color or (255, 255, 255))
            self.lights.color(rgb, zone=zone)
            if track:
                self.state.light_effect, self.state.light_color = "static", list(rgb)

        if brightness is not None:
            self.state.light_brightness = brightness

        if on is False:
            self.lights.off()
            self.state.light_on = False
            self.state.lights_manual = "off"   # override the night schedule until next boundary
        elif on is True or brightness is not None or appearance_changed:
            # turning on, or changing appearance/brightness, implies lights on.
            b = self.state.light_brightness or self.config.light_on_brightness
            self.lights.set_brightness(b)
            self.state.light_brightness, self.state.light_on = b, True
            self.state.lights_manual = "on"

        self._persist()
        return self.status()

    def scheduled_lights(self, on: bool) -> None:
        """Apply a schedule-driven on/off WITHOUT clobbering the saved appearance."""
        if not self.lights.available():
            return
        if on:
            self._apply_appearance()
            self.lights.set_brightness(self.state.light_brightness or self.config.light_on_brightness)
        else:
            self.lights.off()

    def set_night(
        self,
        enabled: bool | None = None,
        clear_manual: bool = False,
        start: str | None = None,
        end: str | None = None,
    ) -> dict:
        if enabled is not None:
            self.state.night_enabled = enabled
        if clear_manual:
            self.state.lights_manual = None
        if start is not None:
            self.state.night_start = start
        if end is not None:
            self.state.night_end = end
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
                "night_start": self.night_window()[0],
                "night_end": self.night_window()[1],
                "brightness": self.state.light_brightness,
                "color": self.state.light_color,
                "effect": self.state.light_effect,
                "on": bool(self.state.light_on),
            },
        }
