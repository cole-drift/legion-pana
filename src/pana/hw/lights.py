from __future__ import annotations

from typing import Callable

from . import spectrum
from .hid import HidTransport
from .transport import Sysfs

HIDRAW_UEVENT_GLOB = "/sys/class/hidraw/hidraw*/device/uevent"
SPECTRUM_VID = "048D"
SPECTRUM_PIDS = {"C193", "C197"}
# vendor usage page 0xFF89 marker in the HID report descriptor — identifies the
# Spectrum *effect* interface. Brightness works on both c193 and c197, but the
# EffectChange (0xCB) engine only lives on c197 / the FF89 collection.
FF89_MARKER = b"\x06\x89\xff"

Opener = Callable[[str], HidTransport]


def _parse_hid_id(uevent_text: str) -> tuple[str, str] | None:
    # HID_ID=0003:0000048D:0000C193  ->  ("048D", "C193")
    for line in uevent_text.splitlines():
        if line.startswith("HID_ID="):
            parts = line.split("=", 1)[1].split(":")
            if len(parts) == 3:
                return parts[1][-4:].upper(), parts[2][-4:].upper()
    return None


class Lights:
    """Spectrum keyboard lighting over hidraw.

    Device selection targets the EFFECT-capable interface (c197 + the 0xFF89 report
    descriptor) — NOT merely "first device that answers GetBrightness", because both
    c193 and c197 answer brightness while only c197 honors EffectChange (0xCB).
    """

    def __init__(self, fs: Sysfs, opener: Opener):
        self.fs = fs
        self.opener = opener
        self._dev: HidTransport | None = None
        self._path: str | None = None

    def candidates(self) -> list[str]:
        """Spectrum lighting devices, ranked: c197+FF89 first, then any FF89, then c197."""
        ranked: list[tuple[int, str]] = []
        for uevent in self.fs.glob(HIDRAW_UEVENT_GLOB):
            node = uevent[: -len("/device/uevent")]
            name = node.rsplit("/", 1)[1]
            ids = _parse_hid_id(self.fs.read(uevent))
            if not (ids and ids[0] == SPECTRUM_VID and ids[1] in SPECTRUM_PIDS):
                continue
            try:
                has_marker = FF89_MARKER in self.fs.read_bytes(node + "/device/report_descriptor")
            except OSError:
                has_marker = False
            if ids[1] == "C197" and has_marker:
                rank = 0
            elif has_marker:
                rank = 1
            elif ids[1] == "C197":
                rank = 2
            else:
                continue  # c193 without the FF89 marker can't drive effects — skip
            ranked.append((rank, "/dev/" + name))
        return [p for _, p in sorted(ranked)]

    def available(self) -> bool:
        return bool(self.candidates())

    def connect(self) -> str:
        if self._dev is not None and self._path is not None:
            return self._path
        for path in self.candidates():
            try:
                self._dev, self._path = self.opener(path), path
                return path
            except OSError:
                continue
        raise RuntimeError("no Spectrum effect device (c197/FF89) found")

    def _send(self, data: bytes) -> None:
        self.connect()
        assert self._dev is not None
        self._dev.send_feature(data)

    def get_brightness(self) -> int:
        self.connect()
        assert self._dev is not None
        self._dev.send_feature(spectrum.get_brightness_request())
        resp = self._dev.get_feature(spectrum.REPORT_SIZE, spectrum.REPORT_ID)
        return spectrum.parse_brightness_response(resp)

    def _profile(self) -> int:
        """Read the device's current profile (effects must be written into it)."""
        self.connect()
        assert self._dev is not None
        self._dev.send_feature(spectrum.get_profile_request())
        resp = self._dev.get_feature(spectrum.REPORT_SIZE, spectrum.REPORT_ID)
        return spectrum.parse_profile_response(resp)

    def _ensure_lit(self) -> None:
        """A correct effect at brightness 0 is invisible — floor it so the change shows."""
        try:
            if self.get_brightness() == 0:
                self.set_brightness(3)
        except OSError:
            pass

    def set_brightness(self, level: int) -> None:
        self._send(spectrum.set_brightness(level))

    def off(self) -> None:
        self.set_brightness(0)

    def logo(self, on: bool) -> None:
        self._send(spectrum.set_logo(on))

    def _zone_keys(self, zone: str) -> list[int]:
        return spectrum.ZONES.get(zone, spectrum.KEYBOARD_KEYS)

    def _keys(self, zone: str, keycodes: list[int] | None) -> list[int]:
        return keycodes if keycodes is not None else self._zone_keys(zone)

    def enumerate_keys(self) -> dict:
        """Ask the controller which LEDs it actually has (KeyCount 0xC4 + KeyPage 0xC5).

        Returns {height, width, keycodes}. Reveals any LED not in the hardcoded tables
        (e.g. a power-button LED that the Pro's keycode list doesn't include).
        """
        self.connect()
        assert self._dev is not None
        self._dev.send_feature(spectrum.keycount_request())
        kc = self._dev.get_feature(spectrum.REPORT_SIZE, spectrum.REPORT_ID)
        height, width = spectrum.parse_keycount_response(kc)
        keys: list[int] = []
        for y in range(max(1, min(height, 16))):
            self._dev.send_feature(spectrum.keypage_request(y, 0x07))
            keys += spectrum.parse_keypage_response(
                self._dev.get_feature(spectrum.REPORT_SIZE, spectrum.REPORT_ID))
        self._dev.send_feature(spectrum.keypage_request(0, 0x08))
        keys += spectrum.parse_keypage_response(
            self._dev.get_feature(spectrum.REPORT_SIZE, spectrum.REPORT_ID))
        return {"height": height, "width": width, "keycodes": sorted(set(keys))}

    def color(self, rgb, zone: str = "keyboard", keycodes: list[int] | None = None) -> None:
        self._send(spectrum.static_color(rgb, self._keys(zone, keycodes), profile=self._profile()))
        if tuple(rgb) != (0, 0, 0):  # setting a zone to black = turn it off; don't relight
            self._ensure_lit()

    def rainbow(self, speed: int = 2, zone: str = "keyboard", keycodes: list[int] | None = None) -> None:
        self._send(spectrum.rainbow(self._keys(zone, keycodes), speed=speed, profile=self._profile()))
        self._ensure_lit()

    def breathe(self, rgb, speed: int = 2, zone: str = "keyboard", keycodes: list[int] | None = None) -> None:
        self._send(spectrum.breathe(rgb, self._keys(zone, keycodes), speed=speed, profile=self._profile()))
        self._ensure_lit()
