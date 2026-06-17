from datetime import time

from pana.core.scheduler import desired_lights, is_night


def test_is_night_wrapping_window():
    # 20:00 -> 07:00 wraps midnight
    assert is_night(time(23, 0), "20:00", "07:00") is True
    assert is_night(time(3, 0), "20:00", "07:00") is True
    assert is_night(time(12, 0), "20:00", "07:00") is False
    assert is_night(time(7, 0), "20:00", "07:00") is False  # end exclusive
    assert is_night(time(20, 0), "20:00", "07:00") is True  # start inclusive


def test_is_night_same_day_window():
    assert is_night(time(13, 0), "12:00", "14:00") is True
    assert is_night(time(15, 0), "12:00", "14:00") is False


def test_desired_lights_schedule():
    assert desired_lights(time(23, 0), True, "20:00", "07:00") == "off"
    assert desired_lights(time(12, 0), True, "20:00", "07:00") == "on"


def test_desired_lights_disabled_has_no_opinion():
    assert desired_lights(time(23, 0), False, "20:00", "07:00") is None


def test_manual_override_wins():
    assert desired_lights(time(23, 0), True, "20:00", "07:00", manual_override="on") == "on"
    assert desired_lights(time(12, 0), True, "20:00", "07:00", manual_override="off") == "off"
