from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Preset:
    """A named bundle of hardware settings.

    `rapl_cap` applies the eco RAPL power cap; non-cap presets restore the RAPL
    default. `lights`/`battery` are None = leave as-is. (Custom per-watt limits go
    through Manager.set_tdp, not a preset.)
    """

    name: str
    platform_profile: str
    rapl_cap: bool = False  # apply the eco RAPL power cap (the real cooling lever)
    lights: str | None = None  # "on" | "off" | None
    battery: str | None = None  # "cap" | "off" | None


def default_presets() -> dict[str, Preset]:
    return {
        # off-grid default: low-power profile (cosmetic/button color) + RAPL cap (actual
        # cooling), lights off, conservation on.
        "eco": Preset("eco", "low-power", rapl_cap=True, lights="off", battery="cap"),
        "balanced": Preset("balanced", "balanced"),
        # full performance, RAPL uncapped, lights on, charge to 100 for unplugged gaming.
        "game": Preset("game", "performance", lights="on", battery="off"),
    }
