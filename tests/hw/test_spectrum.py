import pytest

from pana.hw import spectrum as s


def test_make_request_size_and_header():
    req = s.make_request(s.OP_SET_BRIGHTNESS, bytes([5]))
    assert len(req) == s.REPORT_SIZE
    assert req[:4] == bytes([0x07, 0xCE, 0xC0, 0x03])
    assert req[4] == 5
    assert req[5:] == b"\x00" * (s.REPORT_SIZE - 5)


def test_make_request_rejects_oversize():
    with pytest.raises(ValueError):
        s.make_request(0xCB, b"\x00" * s.REPORT_SIZE)


def test_set_brightness_bounds():
    assert s.set_brightness(0)[4] == 0
    assert s.set_brightness(9)[4] == 9
    with pytest.raises(ValueError):
        s.set_brightness(10)


def test_parse_brightness_response():
    resp = bytes([0x07, 0, 0, 0, 7]) + b"\x00" * 955
    assert s.parse_brightness_response(resp) == 7


def test_set_logo():
    assert s.set_logo(True)[:5] == bytes([0x07, 0xA6, 0xC0, 0x03, 1])
    assert s.set_logo(False)[4] == 0


def test_rainbow_effect_no_colors():
    req = s.rainbow()
    assert req[:4] == bytes([0x07, 0xCB, 0xC0, 0x03])
    body = req[4:]
    assert body[0:3] == bytes([0x00, 0x01, 0x01])
    assert body[3] == 1                              # effect number
    assert body[4:7] == bytes([0x06, 0x01, s.EFFECT_RAINBOW_WAVE])
    assert body[17] == 0                             # num colors (random)


def test_breathe_effect_one_color():
    body = s.breathe((10, 20, 30))[4:]
    assert body[4:7] == bytes([0x06, 0x01, s.EFFECT_COLOR_PULSE])
    assert body[17] == 1                             # num colors
    assert body[18:21] == bytes([10, 20, 30])


def test_static_color_layout():
    req = s.static_color((255, 0, 128), [s.KEYCODE_ALL])
    assert req[:4] == bytes([0x07, 0xCB, 0xC0, 0x03])
    # payload: [profile=0, 0x01, 0x01, effect_no=1, <13B header>, num_colors=1, R,G,B, num_keys=1, kc_lo, kc_hi]
    body = req[4:]
    assert body[0:3] == bytes([0x00, 0x01, 0x01])
    assert body[3] == 1  # effect number
    header = body[4:17]
    assert header[0:3] == bytes([0x06, 0x01, s.EFFECT_STATIC])
    assert body[17] == 1  # num colors
    assert body[18:21] == bytes([255, 0, 128])
    assert body[21] == 1  # num keys
    assert body[22:24] == bytes([0x65, 0x00])  # KEYCODE_ALL little-endian
