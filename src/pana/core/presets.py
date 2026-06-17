from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Preset:
    """A power mode: a platform_profile (cosmetic — sets the power-button color) plus
    a CPU clock-ceiling cap looked up from config by name. Battery and lights are
    controlled separately, NOT bundled into modes.
    """

    name: str
    platform_profile: str


def default_presets() -> dict[str, Preset]:
    return {
        "eco": Preset("eco", "low-power"),          # coolest — power button white
        "balanced": Preset("balanced", "balanced"),  # moderate — power button blue
        "performance": Preset("performance", "performance"),  # full — power button red
    }


# accepted aliases for mode names (muscle memory / old names)
MODE_ALIASES = {"game": "performance"}
