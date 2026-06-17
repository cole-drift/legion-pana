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

# "all lights" pseudo-keycode — reserved for AudioBounce/AudioRipple/AuroraSync ONLY;
# static/rainbow/breathe must enumerate the real per-key codes below, or nothing lights.
KEYCODE_ALL = 0x0065

# Real per-key keycodes for the Legion 7/Pro 7 16IAX10(H) keyboard, from the proven
# legion-spectrum-control tool. Static/breathe/wave effects address THIS set.
KEYBOARD_KEYS = [
    0x0001, 0x0002, 0x0003, 0x0004, 0x0005, 0x0006, 0x0007, 0x0008,
    0x0009, 0x000A, 0x000B, 0x000C, 0x000D, 0x000E, 0x000F, 0x0010,
    0x0011, 0x0012, 0x0013, 0x0014, 0x0016, 0x0017, 0x0018, 0x0019,
    0x001A, 0x001B, 0x001C, 0x001D, 0x001E, 0x001F, 0x0020, 0x0021,
    0x0022, 0x0026, 0x0027, 0x0028, 0x0029, 0x0038, 0x0040, 0x0042,
    0x0043, 0x0044, 0x0045, 0x0046, 0x0047, 0x0048, 0x0049, 0x004A,
    0x004B, 0x004C, 0x004D, 0x004E, 0x004F, 0x0050, 0x0051, 0x0055,
    0x0058, 0x0059, 0x005A, 0x005B, 0x005C, 0x005D, 0x005F, 0x0068,
    0x006A, 0x006D, 0x006E, 0x006F, 0x0070, 0x0071, 0x0072, 0x0073,
    0x0074, 0x0075, 0x0076, 0x0077, 0x0079, 0x007B, 0x007C, 0x007F,
    0x0080, 0x0082, 0x0083, 0x0087, 0x0088, 0x008D, 0x008E, 0x0090,
    0x0092, 0x0096, 0x0097, 0x0098, 0x009A, 0x009B, 0x009C, 0x009D,
    0x009F, 0x00A1, 0x00A3, 0x00A5, 0x00A7,
]

# Perimeter accent LEDs. The "rear accent" runs along the hinge — i.e. the lit strip
# ABOVE the keyboard (the power-button area). Side+front accent are the lower edge.
PERIMETER_REAR = [
    0x03E9, 0x03EA, 0x03EB, 0x03EC, 0x03ED, 0x03EE, 0x03EF, 0x03F0, 0x03F1,
    0x03F2, 0x03F3, 0x03F4, 0x03F5, 0x03F6, 0x03F7, 0x03F8, 0x03F9, 0x03FA,
]
PERIMETER_FRONT = [0x01F5, 0x01F6, 0x01F7, 0x01F8, 0x01F9, 0x01FA, 0x01FB, 0x01FC, 0x01FD, 0x01FE]
PERIMETER_KEYS = PERIMETER_REAR + PERIMETER_FRONT
LOGO_KEY = 0x05DD  # single LED behind the lid "LEGION" text

ZONES = {
    "keyboard": KEYBOARD_KEYS,
    "perimeter": PERIMETER_KEYS,
    "rear": PERIMETER_REAR,      # the strip above the keyboard / power-button area
    "logo": [LOGO_KEY],
    "all": KEYBOARD_KEYS + PERIMETER_KEYS + [LOGO_KEY],
}


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


def get_profile_request() -> bytes:
    return make_request(OP_PROFILE_GET)


def parse_profile_response(resp: bytes) -> int:
    return resp[4]


def keycount_request(param: int = 0x07) -> bytes:
    return make_request(OP_KEYCOUNT, bytes([param]))


def parse_keycount_response(resp: bytes) -> tuple[int, int]:
    # (indexes / height, keys-per-index / width)
    return resp[5], resp[6]


def keypage_request(index: int, param: int = 0x07) -> bytes:
    return make_request(OP_KEYPAGE, bytes([param, index]))


def parse_keypage_response(resp: bytes, count: int = 32) -> list[int]:
    # items start at offset 6: each is {index:u8, keycode:u16-le} = 3 bytes. keycode>0 = a real LED.
    keys: list[int] = []
    for i in range(count):
        off = 6 + i * 3
        if off + 2 >= len(resp):
            break
        kc = resp[off + 1] | (resp[off + 2] << 8)
        if kc:
            keys.append(kc)
    return keys


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
    speed: int = 0,
    clockwise: int = 0,
    direction: int = 0,
    color_mode: int | None = None,
    profile: int = 0,
) -> bytes:
    """Build an EffectChange (0xCB) request for an arbitrary effect/colors/zone.

    Defaults to the enumerated KEYBOARD_KEYS — addressing only KEYCODE_ALL (0x65) does
    NOT light anything for static/wave/breathe (that pseudo-code is audio-effects only).
    `profile` must be the device's CURRENT profile (read via get_profile_request).
    """
    colors = colors or []
    keycodes = keycodes if keycodes is not None else KEYBOARD_KEYS
    if color_mode is None:
        color_mode = (
            COLOR_MODE_LIST if colors
            else (COLOR_MODE_RANDOM if effect_type != EFFECT_STATIC else COLOR_MODE_NONE)
        )
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


def static_color(rgb: tuple[int, int, int], keycodes: list[int] | None = None, *, profile: int = 0) -> bytes:
    return build_effect(EFFECT_STATIC, colors=[rgb], keycodes=keycodes,
                        color_mode=COLOR_MODE_LIST, profile=profile)


def rainbow(keycodes: list[int] | None = None, *, speed: int = 2, direction: int = 4, profile: int = 0) -> bytes:
    return build_effect(EFFECT_RAINBOW_WAVE, keycodes=keycodes, speed=speed,
                        direction=direction, color_mode=COLOR_MODE_RANDOM, profile=profile)


def breathe(rgb: tuple[int, int, int], keycodes: list[int] | None = None, *, speed: int = 2, profile: int = 0) -> bytes:
    return build_effect(EFFECT_COLOR_PULSE, colors=[rgb], keycodes=keycodes, speed=speed,
                        color_mode=COLOR_MODE_LIST, profile=profile)
