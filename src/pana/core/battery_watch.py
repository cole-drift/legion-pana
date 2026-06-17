from __future__ import annotations

import asyncio


def decide(
    capacity: int | None,
    target: int | None,
    conservation_on: bool | None,
    hysteresis: int = 3,
) -> bool | None:
    """Decide the next conservation toggle to hold `target` with hysteresis.

    Returns True (enable cap / stop charging), False (disable / allow charging),
    or None (no change). Note: physically this can only hold targets at or above
    the firmware conservation cap (~60-80%); below that the cap can't brake.
    """
    if target is None or capacity is None:
        return None
    if capacity >= target:
        return None if conservation_on else True
    if capacity <= target - hysteresis:
        return None if not conservation_on else False
    return None


class BatteryWatcher:
    """Polls capacity and toggles conservation to hold a soft target."""

    def __init__(self, battery, get_target, hysteresis: int = 3, interval: float = 30.0):
        self.battery = battery
        self.get_target = get_target
        self.hysteresis = hysteresis
        self.interval = interval

    def tick(self) -> bool | None:
        action = decide(
            self.battery.capacity(),
            self.get_target(),
            self.battery.conservation(),
            self.hysteresis,
        )
        if action is not None:
            self.battery.set_conservation(action)
        return action

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                self.tick()
            except Exception:  # a transient sysfs hiccup must not kill the loop
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass
