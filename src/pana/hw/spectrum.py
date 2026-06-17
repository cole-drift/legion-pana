"""Pure encoder for the Lenovo Spectrum keyboard-lighting HID protocol.

960-byte feature reports, report id 0x07, 4-byte header [0x07, op, 0xC0, 0x03].
No I/O here — every function returns bytes; transport lives in hw.hid.
Protocol facts sourced from LenovoLegionToolkit + legion-spectrum-control (see spec).
"""
from __future__ import annotations

import struct

REPORT_ID = 0x07
REPORT_SIZE = 960
_SIZE_BYTE = 0xC0
_TAIL = 0x03

# operation types
OP_KEYCOUNT = 0xC4
OP_KEYPAGE = 0xC5
OP_PROFILE_GET = 0xCA
OP_EFFECT_CHANGE = 0xCB
OP_GET_BRIGHTNESS = 0xCD
OP_SET_BRIGHTNESS = 0xCE
OP_GET_LOGO = 0xA5
OP_SET_LOGO = 0xA6

EFFECT_RAINBOW_WAVE = 2
EFFECT_COLOR_PULSE = 4  # "breathing"
EFFECT_STATIC = 11  # "Always" / static color

COLOR_MODE_NONE = 0
COLOR_MODE_RANDOM = 1
COLOR_MODE_LIST = 2

# "all lights" pseudo-keycode (whole keyboard); per legion-spectrum-control.
KEYCODE_ALL = 0x0065


def make_request(op: int, payload: bytes = b"") -> bytes:
    header = bytes([REPORT_ID, op, _SIZE_BYTE, _TAIL])
    body = header + payload
    if len(body) > REPORT_SIZE:
        raise ValueError(f"payload too large: {len(body)} > {REPORT_SIZE}")
    return body.ljust(REPORT_SIZE, b"\x00")


def set_brightness(level: int) -> bytes:
    if not 0 <= level <= 9:
        raise ValueError("brightness level must be 0-9")
    return make_request(OP_SET_BRIGHTNESS, bytes([level]))


def get_brightness_request() -> bytes:
    return make_request(OP_GET_BRIGHTNESS)


def parse_brightness_response(resp: bytes) -> int:
    return resp[4]


def set_logo(on: bool) -> bytes:
    return make_request(OP_SET_LOGO, bytes([1 if on else 0]))


def keycount_request() -> bytes:
    return make_request(OP_KEYCOUNT)


def parse_keycount_response(resp: bytes) -> tuple[int, int]:
    # (indexes/width, keys-per-index/height); byte offsets provisional, confirm live.
    return resp[5], resp[6]


def _effect_header(
    effect_type: int = EFFECT_STATIC,
    speed: int = 0,
    clockwise: int = 0,
    direction: int = 0,
    color_mode: int = COLOR_MODE_LIST,
) -> bytes:
    return bytes(
        [0x06, 0x01, effect_type, 0x02, speed, 0x03, clockwise,
         0x04, direction, 0x05, color_mode, 0x06, 0x00]
    )


def build_effect(
    effect_type: int,
    colors: list[tuple[int, int, int]] | None = None,
    keycodes: list[int] | None = None,
    *,
    speed: int = 1,
    clockwise: int = 0,
    direction: int = 1,
    color_mode: int | None = None,
    profile: int = 0,
) -> bytes:
    """Build an EffectChange (0xCB) request for an arbitrary effect/colors/zone."""
    colors = colors or []
    keycodes = keycodes if keycodes is not None else [KEYCODE_ALL]
    if color_mode is None:
        color_mode = COLOR_MODE_LIST if colors else COLOR_MODE_RANDOM
    blob = bytes([1])  # effect number
    blob += _effect_header(effect_type, speed, clockwise, direction, color_mode)
    blob += bytes([len(colors)])
    for r, g, b in colors:
        blob += bytes([r, g, b])
    blob += bytes([len(keycodes)])
    for kc in keycodes:
        blob += struct.pack("<H", kc)
    payload = bytes([profile, 0x01, 0x01]) + blob
    return make_request(OP_EFFECT_CHANGE, payload)


def static_color(rgb: tuple[int, int, int], keycodes: list[int] | None = None) -> bytes:
    return build_effect(EFFECT_STATIC, colors=[rgb], keycodes=keycodes)


def rainbow(keycodes: list[int] | None = None, speed: int = 1) -> bytes:
    return build_effect(EFFECT_RAINBOW_WAVE, keycodes=keycodes, speed=speed,
                        color_mode=COLOR_MODE_RANDOM)


def breathe(rgb: tuple[int, int, int], keycodes: list[int] | None = None, speed: int = 1) -> bytes:
    return build_effect(EFFECT_COLOR_PULSE, colors=[rgb], keycodes=keycodes, speed=speed)
