from __future__ import annotations

from dataclasses import asdict, dataclass

from .transport import Sysfs

PLATFORM_PROFILE = "/sys/firmware/acpi/platform_profile"
PLATFORM_PROFILE_CHOICES = "/sys/firmware/acpi/platform_profile_choices"
PPT_DIR = "/sys/class/firmware-attributes/lenovo-wmi-other-0/attributes"
CONSERVATION = "/sys/bus/platform/devices/VPC2004:00/conservation_mode"
CHARGE_TYPES = "/sys/class/power_supply/BAT0/charge_types"


@dataclass
class Capabilities:
    power_modes: bool
    profile_choices: list[str]
    ppt: bool
    ppt_attrs: list[str]
    battery_conservation: bool

    def to_dict(self) -> dict:
        return asdict(self)


def detect(fs: Sysfs) -> Capabilities:
    power_modes = fs.exists(PLATFORM_PROFILE)
    choices: list[str] = []
    if fs.exists(PLATFORM_PROFILE_CHOICES):
        choices = fs.read(PLATFORM_PROFILE_CHOICES).split()
    ppt_attrs = [p.split("/")[-2] for p in fs.glob(f"{PPT_DIR}/ppt_*/current_value")]
    battery = fs.exists(CONSERVATION) or fs.exists(CHARGE_TYPES)
    return Capabilities(
        power_modes=power_modes,
        profile_choices=choices,
        ppt=bool(ppt_attrs),
        ppt_attrs=ppt_attrs,
        battery_conservation=battery,
    )
