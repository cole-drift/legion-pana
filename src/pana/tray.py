from __future__ import annotations

import argparse
import asyncio

from .ipc.client import call
from .ipc.protocol import Request

DEFAULT_SOCKET = "/run/pana/pana.sock"

MODES = ["eco", "balanced", "performance"]
MODE_LABELS = {
    "eco": "Eco — coolest (CPU throttled hard)",
    "balanced": "Balanced — moderate CPU ceiling",
    "performance": "Performance — full power (no cap)",
}
NIGHT_WINDOWS = [
    ("8pm – 7am", ("20:00", "07:00")),
    ("9pm – 7am", ("21:00", "07:00")),
    ("10pm – 6am", ("22:00", "06:00")),
    ("11pm – 8am", ("23:00", "08:00")),
]
LIGHT_LEVELS = [("Low", 2), ("Medium", 5), ("High", 9)]
LIGHT_COLORS = [
    ("White", (255, 255, 255)), ("Red", (255, 0, 0)), ("Orange", (255, 80, 0)),
    ("Yellow", (255, 200, 0)), ("Green", (0, 255, 0)), ("Cyan", (0, 255, 255)),
    ("Blue", (0, 0, 255)), ("Purple", (150, 90, 220)), ("Pink", (255, 40, 150)),
]
LIGHT_EFFECTS = [("Static color", "static"), ("Rainbow", "rainbow"), ("Breathing", "breathe")]


class TempTrend:
    """Rolling CPU-temp tracker for the tray's live label.

    A short-window mean gives a steady reading instead of a flickering snapshot;
    a longer-window max gives a 'recent peak' so a brief spike stays visible.
    Timestamps (monotonic seconds) are passed in, so this stays pure + testable.
    """

    def __init__(self, smooth_s: float = 2.0, peak_s: float = 60.0):
        self.smooth_s = smooth_s
        self.peak_s = peak_s
        self._samples: list[tuple[float, float]] = []

    def add(self, ts: float, temp: float | None) -> None:
        if temp is None:
            return
        self._samples.append((ts, temp))
        cutoff = ts - self.peak_s
        self._samples = [(t, v) for t, v in self._samples if t >= cutoff]

    def smoothed(self) -> float | None:
        if not self._samples:
            return None
        latest = self._samples[-1][0]
        window = [v for t, v in self._samples if t >= latest - self.smooth_s]
        return round(sum(window) / len(window), 1) if window else None

    def peak(self) -> float | None:
        if not self._samples:
            return None
        return max(v for _, v in self._samples)


def _title(status: dict, temp_c: float | None = None, peak_c: float | None = None) -> str:
    bat = status.get("battery") or {}
    mon = status.get("monitor") or {}
    cap = (status.get("cpu_cap") or {}).get("max_perf_pct")
    parts = [f"pana — {status.get('mode') or '?'}"]
    if cap is not None:
        parts.append(f"CPU {cap}%")
    if bat.get("capacity") is not None:
        parts.append(f"{bat['capacity']}%")
    t = temp_c if temp_c is not None else mon.get("cpu_temp_c")
    if t is not None:
        tok = f"{t:g}°C"
        if peak_c is not None:
            tok += f" (pk {peak_c:g}°)"
        parts.append(tok)
    if mon.get("cpu_power_w") is not None:
        parts.append(f"{mon['cpu_power_w']:g}W")
    return "  ·  ".join(parts)


def menu_model(status: dict) -> list[dict]:
    """Backend-agnostic, possibly-nested menu description (pure + testable).

    Item types: 'label', 'separator', 'submenu' (has 'items'), or an actionable
    item ('text' + 'cmd' + 'args', optional 'checked'/'radio'), or a special
    {'action': 'quit'|'refresh'}.
    """
    mode = status.get("mode")
    bat = status.get("battery") or {}
    lights = status.get("lights") or {}
    cons = bat.get("conservation")
    cur_color = lights.get("color")
    cur_effect = lights.get("effect")
    cur_bri = lights.get("brightness")
    on = lights.get("on")

    items: list[dict] = [
        {"type": "label", "text": _title(status)},
        {"type": "separator"},
    ]
    for m in MODES:
        items.append({"text": MODE_LABELS[m], "cmd": "mode", "args": {"name": m},
                      "checked": mode == m, "radio": True})
    items.append({"type": "separator"})

    if lights.get("available"):
        light_items: list[dict] = [
            {"text": "On", "cmd": "lights", "args": {"on": True}, "checked": on is True, "radio": True},
            {"text": "Off", "cmd": "lights", "args": {"on": False}, "checked": on is False, "radio": True},
            {"type": "separator"},
            {"type": "submenu", "text": "Brightness", "items": [
                {"text": lbl, "cmd": "lights", "args": {"brightness": lv},
                 "checked": cur_bri == lv, "radio": True} for lbl, lv in LIGHT_LEVELS
            ]},
            {"type": "submenu", "text": "Color", "items": [
                {"text": nm, "cmd": "lights", "args": {"color": list(rgb), "effect": "static"},
                 "checked": cur_effect == "static" and cur_color == list(rgb), "radio": True}
                for nm, rgb in LIGHT_COLORS
            ]},
            {"type": "submenu", "text": "Effect", "items": [
                {"text": nm, "cmd": "lights", "args": {"effect": ef},
                 "checked": cur_effect == ef, "radio": True} for nm, ef in LIGHT_EFFECTS
            ]},
        ]
        items.append({"type": "submenu", "text": "Lighting", "items": light_items})
    else:
        items.append({"type": "label", "text": "Lighting: (no device found)"})

    nstart = lights.get("night_start", "?")
    nend = lights.get("night_end", "?")
    night_on = bool(lights.get("night_enabled"))
    night_items: list[dict] = [
        {"text": "Enabled", "cmd": "night", "args": {"enabled": True}, "checked": night_on, "radio": True},
        {"text": "Disabled", "cmd": "night", "args": {"enabled": False}, "checked": not night_on, "radio": True},
        {"type": "separator"},
        {"type": "label", "text": "Window:"},
    ]
    for lbl, (s, e) in NIGHT_WINDOWS:
        night_items.append({"text": lbl, "cmd": "night", "args": {"start": s, "end": e},
                            "checked": (nstart, nend) == (s, e), "radio": True})
    items.append({"type": "submenu", "text": f"Night auto-off  ({nstart}–{nend})", "items": night_items})
    items.append({"type": "separator"})
    items.append({"text": "Battery: conserve (~80% cap)", "cmd": "battery", "args": {"cap": True},
                  "checked": cons is True, "radio": True})
    items.append({"text": "Battery: full charge (100%)", "cmd": "battery", "args": {"off": True},
                  "checked": cons is False, "radio": True})
    items.append({"type": "separator"})
    items.append({"text": "Refresh", "action": "refresh"})
    items.append({"text": "Quit", "action": "quit"})
    return items


def _send(socket: str, cmd: str, args: dict) -> None:
    try:
        asyncio.run(call(socket, Request(cmd=cmd, args=args)))
    except OSError:
        pass


def _fetch_status(socket: str) -> dict:
    try:
        resp = asyncio.run(call(socket, Request(cmd="status")))
        return resp.data if resp.ok else {}
    except OSError:
        return {}


def run(socket: str = DEFAULT_SOCKET) -> None:  # pragma: no cover - GUI glue
    import threading
    import time

    import pystray
    from PIL import Image, ImageDraw

    try:
        from gi.repository import GLib
    except Exception:  # noqa: BLE001 - non-GTK backend: live label updates disabled
        GLib = None

    def icon_image() -> "Image.Image":
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=(150, 90, 220))
        return img

    cache = {"status": _fetch_status(socket)}
    trend = TempTrend()
    stop = threading.Event()

    def refresh() -> None:
        cache["status"] = _fetch_status(socket)

    def live_title() -> str:
        st = cache["status"]
        mon = st.get("monitor") or {}
        trend.add(time.monotonic(), mon.get("cpu_temp_c"))
        return _title(st, temp_c=trend.smoothed(), peak_c=trend.peak())

    def to_items(model):
        out = []
        for it in model:
            kind = it.get("type")
            if kind == "separator":
                out.append(pystray.Menu.SEPARATOR)
            elif kind == "label":
                out.append(pystray.MenuItem(it["text"], None, enabled=False))
            elif kind == "submenu":
                out.append(pystray.MenuItem(it["text"], pystray.Menu(*to_items(it["items"]))))
            elif it.get("action") == "quit":
                out.append(pystray.MenuItem(it["text"], lambda ic, item: (stop.set(), ic.stop())))
            elif it.get("action") == "refresh":
                out.append(pystray.MenuItem(it["text"], lambda ic, item: rebuild(ic)))
            else:
                act = (lambda c, a: lambda ic, item: click(ic, c, a))(it["cmd"], it["args"])
                checked = (lambda v: lambda item: v)(it["checked"]) if "checked" in it else None
                out.append(pystray.MenuItem(it["text"], act, checked=checked, radio=it.get("radio", False)))
        return out

    def build():
        return pystray.Menu(*to_items(menu_model(cache["status"])))

    def rebuild(ic) -> None:
        refresh()
        ic.menu = build()
        ic.update_menu()
        try:
            ic.title = _title(cache["status"])
        except Exception:
            pass

    def click(ic, cmd, args) -> None:
        _send(socket, cmd, args)
        rebuild(ic)

    def update_label() -> bool:
        # Edit ONLY the top label's text in place. dbusmenu pushes that single
        # property change to GNOME without recreating the menu, so the telemetry
        # ticks live even while the menu is open and no open submenu collapses.
        # (Rebuilding the whole menu on a timer is what used to kick you out.)
        h = getattr(icon, "_menu_handle", None)
        if h is not None:
            kids = h.get_children()
            if kids:
                try:
                    kids[0].set_label(live_title())
                except Exception:
                    pass
        return False  # one-shot GLib idle callback

    def live_loop(ic) -> None:
        # pystray runs setup in a worker thread once the icon is ready; a custom
        # setup replaces the default, so we flip visibility on ourselves.
        ic.visible = True
        while not stop.wait(1.0):
            refresh()
            if GLib is not None:
                GLib.idle_add(update_label)  # marshal the GTK call onto the main loop

    icon = pystray.Icon("pana", icon_image(), "pana", menu=build())
    # Telemetry in the top label refreshes live (1s) by editing that one item in
    # place — never by rebuilding the menu (that collapsed open submenus). The rest
    # of the menu still rebuilds only on a click or "Refresh", when it's closing.
    try:
        icon.title = _title(cache["status"])
    except Exception:
        pass
    icon.run(setup=live_loop)


def main() -> None:
    parser = argparse.ArgumentParser(prog="pana-tray")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    run(parser.parse_args().socket)
