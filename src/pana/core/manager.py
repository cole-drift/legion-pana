from __future__ import annotations

from typing import Callable

from ..hw.battery import Battery
from ..hw.hid import HidTransport, RealHid
from ..hw.lights import Lights
from ..hw.platform_profile import PlatformProfile
from ..hw.rapl import Rapl
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
        self.rapl = Rapl(self.fs)
        self.battery = Battery(self.fs)
        self.sensors = Sensors(self.fs)
        self.lights = Lights(self.fs, lights_opener or (lambda path: RealHid(path)))
        self.config = config or Config()
        self.state = state or State()
        self.presets = presets or default_presets()
        # RAPL caps we want held (against thermald resets); None = don't enforce.
        self._desired_rapl: dict | None = None
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
        # the actual cooling lever: Intel RAPL package power cap.
        if self.rapl.available():
            if p.rapl_cap:
                self.rapl.set_pl1_w(self.config.eco_pl1_w)
                self.rapl.set_pl2_w(self.config.eco_pl2_w)
                self._desired_rapl = {"pl1": self.config.eco_pl1_w, "pl2": self.config.eco_pl2_w}
            else:
                self.rapl.set_pl1_w(self.config.uncap_pl1_w)
                self.rapl.set_pl2_w(self.config.uncap_pl2_w)
                self._desired_rapl = None  # uncapped: let thermald manage, don't enforce
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
        if not self.rapl.available():
            raise RuntimeError("RAPL power-cap not available on this machine")
        desired = dict(self._desired_rapl or {})
        if pl1 is not None:
            desired["pl1"] = self.rapl.set_pl1_w(pl1)
        if pl2 is not None:
            desired["pl2"] = self.rapl.set_pl2_w(pl2)
        self._desired_rapl = desired
        self.state.mode = "custom"
        self.state.custom_pl1 = desired.get("pl1")
        self.state.custom_pl2 = desired.get("pl2")
        self._persist()
        return self.status()

    def enforce_rapl(self) -> None:
        """Re-assert an active cap if thermald (or anything) raised the limit back up.

        Only pushes the limit DOWN to the desired cap — never fights thermald when it
        lowers the limit for thermal safety.
        """
        if not self._desired_rapl or not self.rapl.available():
            return
        cur = self.rapl.get_limits_w()
        for key, setter in (("pl1", self.rapl.set_pl1_w), ("pl2", self.rapl.set_pl2_w)):
            want = self._desired_rapl.get(key)
            have = cur.get(key)
            if want and have and have > want + 0.5:
                _safe(lambda s=setter, w=want: s(w))

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
            if self.rapl.available():
                desired: dict = {}
                if self.state.custom_pl1:
                    desired["pl1"] = _safe(lambda: self.rapl.set_pl1_w(self.state.custom_pl1))
                if self.state.custom_pl2:
                    desired["pl2"] = _safe(lambda: self.rapl.set_pl2_w(self.state.custom_pl2))
                self._desired_rapl = {k: v for k, v in desired.items() if v} or None
        elif self.state.mode:
            _safe(lambda: self._apply_preset(self.presets[self.state.mode]))

    # ---- read-only status ----

    def status(self) -> dict:
        return {
            "mode": self.state.mode,
            "platform_profile": _safe(self.profile.get) if self.profile.available() else None,
            "profile_choices": self.profile.choices(),
            "rapl": {
                "available": self.rapl.available(),
                "limits_w": self.rapl.get_limits_w() if self.rapl.available() else None,
                "desired_w": self._desired_rapl,
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
