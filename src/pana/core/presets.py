from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Preset:
    """A named bundle of hardware settings.

    A non-empty `ppt` implies the custom platform_profile (the manager sets
    'custom' before writing the limits). `lights`/`battery` are None = leave
    as-is.
    """

    name: str
    platform_profile: str
    ppt: dict[str, int] = field(default_factory=dict)
    lights: str | None = None  # "on" | "off" | None
    battery: str | None = None  # "cap" | "off" | None


def default_presets() -> dict[str, Preset]:
    return {
        # off-grid default: BIOS-managed low power (no custom-mode risk), lights off, cap on.
        "eco": Preset("eco", "low-power", lights="off", battery="cap"),
        "balanced": Preset("balanced", "balanced"),
        # full performance, lights on, charge to 100 for unplugged gaming.
        "game": Preset("game", "performance", lights="on", battery="off"),
    }


def custom_tdp_preset(pl1: int | None = None, pl2: int | None = None) -> Preset:
    ppt: dict[str, int] = {}
    if pl1 is not None:
        ppt["ppt_pl1_spl"] = pl1
    if pl2 is not None:
        ppt["ppt_pl2_sppt"] = pl2
    return Preset("custom", "custom", ppt=ppt)
