from __future__ import annotations

from typing import Callable

from . import spectrum
from .hid import HidTransport
from .transport import Sysfs

HIDRAW_UEVENT_GLOB = "/sys/class/hidraw/hidraw*/device/uevent"
SPECTRUM_VID = "048D"
SPECTRUM_PIDS = {"C193", "C197"}

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
    """Spectrum keyboard/perimeter lighting over hidraw.

    The correct device (c193 vs c197) is identified empirically: each candidate
    is probed with GetBrightness and the first returning a sane (0-9) level wins.
    """

    def __init__(self, fs: Sysfs, opener: Opener):
        self.fs = fs
        self.opener = opener
        self._dev: HidTransport | None = None
        self._path: str | None = None

    def candidates(self) -> list[str]:
        out: list[str] = []
        for uevent in self.fs.glob(HIDRAW_UEVENT_GLOB):
            node = uevent[: -len("/device/uevent")]
            name = node.rsplit("/", 1)[1]
            ids = _parse_hid_id(self.fs.read(uevent))
            if ids and ids[0] == SPECTRUM_VID and ids[1] in SPECTRUM_PIDS:
                out.append("/dev/" + name)
        return out

    def available(self) -> bool:
        return bool(self.candidates())

    def connect(self) -> str:
        if self._dev is not None and self._path is not None:
            return self._path
        for path in self.candidates():
            try:
                dev = self.opener(path)
                dev.send_feature(spectrum.get_brightness_request())
                resp = dev.get_feature(spectrum.REPORT_SIZE, spectrum.REPORT_ID)
                if 0 <= spectrum.parse_brightness_response(resp) <= 9:
                    self._dev, self._path = dev, path
                    return path
            except OSError:
                continue
        raise RuntimeError("no responsive Spectrum lighting device found")

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

    def set_brightness(self, level: int) -> None:
        self._send(spectrum.set_brightness(level))

    def off(self) -> None:
        self.set_brightness(0)

    def logo(self, on: bool) -> None:
        self._send(spectrum.set_logo(on))

    def color(self, rgb: tuple[int, int, int], keycodes: list[int] | None = None) -> None:
        keys = keycodes if keycodes is not None else [spectrum.KEYCODE_ALL]
        self._send(spectrum.static_color(rgb, keys))
