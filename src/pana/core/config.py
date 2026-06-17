from __future__ import annotations

import json
import os
import tomllib
from dataclasses import asdict, dataclass

CONFIG_PATH = "/etc/pana/config.toml"
STATE_PATH = "/var/lib/pana/state.json"


@dataclass
class Config:
    """User-authored settings (TOML, read-only for the daemon)."""

    default_mode: str = "balanced"
    battery_target: int | None = None  # soft target %; None = no soft target
    light_on_brightness: int = 3
    # Per-mode CPU clock-ceiling cap (intel_pstate max_perf_pct, 1-100) — the cooling
    # lever that works on this machine. Modes are now a pure CPU ladder; battery and
    # lights are controlled separately.
    eco_pct: int = 50
    balanced_pct: int = 80
    performance_pct: int = 100
    night_enabled: bool = False
    night_start: str = "20:00"
    night_end: str = "07:00"
    auto_on_battery: str | None = None  # mode to apply on DC; None = disabled
    poll_interval_s: int = 30
    monitor_interval_s: int = 2

    @classmethod
    def from_toml(cls, text: str) -> "Config":
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return cls()
        section = data.get("pana", data)
        cfg = cls()
        for key, value in section.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg

    @classmethod
    def load(cls, path: str = CONFIG_PATH) -> "Config":
        try:
            with open(path, encoding="utf-8") as f:
                return cls.from_toml(f.read())
        except FileNotFoundError:
            return cls()


@dataclass
class State:
    """Daemon-persisted runtime state (JSON, machine-written)."""

    mode: str | None = None
    battery_target: int | None = None
    lights_manual: str | None = None  # "on"|"off" manual override of the schedule
    night_enabled: bool | None = None  # None = inherit Config.night_enabled
    custom_max_pct: int | None = None  # clock-ceiling cap for "custom" mode (pana power)
    light_on: bool | None = None         # whether lights are on (preserves brightness/color across off/on)
    light_brightness: int | None = None  # the on-level brightness pana set
    light_color: list | None = None      # last static [r,g,b] pana set
    light_effect: str | None = None      # "static" | "rainbow" | "breathe"
    night_start: str | None = None       # override Config.night_start (e.g. "21:30")
    night_end: str | None = None         # override Config.night_end

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str) -> "State":
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return cls()
        st = cls()
        for key, value in data.items():
            if hasattr(st, key):
                setattr(st, key, value)
        return st

    @classmethod
    def load(cls, path: str = STATE_PATH) -> "State":
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            return cls()
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            # corrupt file -> back it up so we don't lose forensics, then defaults
            try:
                os.replace(path, path + "-old")
            except OSError:
                pass
            return cls()
        st = cls()
        if isinstance(data, dict):
            for key, value in data.items():
                if hasattr(st, key):
                    setattr(st, key, value)
        return st

    def save(self, path: str = STATE_PATH) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        os.replace(tmp, path)
