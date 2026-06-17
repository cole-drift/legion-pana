from __future__ import annotations

from datetime import time


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def is_night(now_t: time, start: str, end: str) -> bool:
    s = _parse_hhmm(start)
    e = _parse_hhmm(end)
    if s <= e:
        return s <= now_t < e
    # window wraps past midnight (e.g. 20:00 -> 07:00)
    return now_t >= s or now_t < e


def desired_lights(
    now_t: time,
    enabled: bool,
    start: str,
    end: str,
    manual_override: str | None = None,
) -> str | None:
    """Return 'off' | 'on' | None (no opinion). A manual override always wins."""
    if manual_override is not None:
        return manual_override
    if not enabled:
        return None
    return "off" if is_night(now_t, start, end) else "on"
