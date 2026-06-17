from __future__ import annotations

from .detect import PLATFORM_PROFILE, PLATFORM_PROFILE_CHOICES
from .transport import Sysfs


class PlatformProfile:
    """Read/write the ACPI platform_profile (power mode) on this machine."""

    def __init__(self, fs: Sysfs):
        self.fs = fs

    def available(self) -> bool:
        return self.fs.exists(PLATFORM_PROFILE)

    def choices(self) -> list[str]:
        if not self.fs.exists(PLATFORM_PROFILE_CHOICES):
            return []
        return self.fs.read(PLATFORM_PROFILE_CHOICES).split()

    def get(self) -> str:
        return self.fs.read(PLATFORM_PROFILE)

    def set(self, profile: str) -> None:
        choices = self.choices()
        if profile not in choices:
            raise ValueError(f"profile {profile!r} not available; choices: {choices}")
        self.fs.write(PLATFORM_PROFILE, profile)
