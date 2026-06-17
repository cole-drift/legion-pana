from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Preset:
    """A named bundle of hardware settings.

    `eco_cap` applies the eco CPU clock-ceiling cap (intel_pstate max_perf_pct);
    non-cap presets restore 100%. `lights`/`battery` are None = leave as-is.
    (Custom clock caps go through Manager.set_power, not a preset.)
    """

    name: str
    platform_profile: str
    eco_cap: bool = False  # apply the eco clock-ceiling cap (the real cooling lever)
    lights: str | None = None  # "on" | "off" | None
    battery: str | None = None  # "cap" | "off" | None


def default_presets() -> dict[str, Preset]:
    return {
        # off-grid default: low-power profile (cosmetic/button color) + clock cap (actual
        # cooling), lights off, conservation on.
        "eco": Preset("eco", "low-power", eco_cap=True, lights="off", battery="cap"),
        "balanced": Preset("balanced", "balanced"),
        # full power: clock ceiling at 100%, lights on, charge to 100.
        "performance": Preset("performance", "performance", lights="on", battery="off"),
    }


# accepted aliases for mode names (muscle memory / old names)
MODE_ALIASES = {"game": "performance"}
