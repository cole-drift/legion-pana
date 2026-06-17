from __future__ import annotations

import argparse
import asyncio

from .ipc.client import call
from .ipc.protocol import Request

DEFAULT_SOCKET = "/run/pana/pana.sock"

MODES = ["eco", "balanced", "performance"]
MODE_LABELS = {
    "eco": "Eco — cool & quiet (CPU capped, lights off, battery conserve)",
    "balanced": "Balanced — default (full clocks, no caps)",
    "performance": "Performance — full power (lights on, charge to 100%)",
}
LIGHT_LEVELS = [("Low", 2), ("Medium", 5), ("High", 9)]
LIGHT_COLORS = [
    ("White", (255, 255, 255)), ("Red", (255, 0, 0)), ("Orange", (255, 80, 0)),
    ("Yellow", (255, 200, 0)), ("Green", (0, 255, 0)), ("Cyan", (0, 255, 255)),
    ("Blue", (0, 0, 255)), ("Purple", (150, 90, 220)), ("Pink", (255, 40, 150)),
]
LIGHT_EFFECTS = [("Static color", "static"), ("Rainbow", "rainbow"), ("Breathing", "breathe")]


def _title(status: dict) -> str:
    bat = status.get("battery") or {}
    mon = status.get("monitor") or {}
    parts = [f"pana — {status.get('mode') or '?'}"]
    if bat.get("capacity") is not None:
        parts.append(f"{bat['capacity']}%")
    if mon.get("cpu_temp_c") is not None:
        parts.append(f"{mon['cpu_temp_c']:g}°C")
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

    items.append({"text": "Night schedule (auto lights off)", "cmd": "night",
                  "args": {"enabled": not bool(lights.get("night_enabled"))},
                  "checked": bool(lights.get("night_enabled"))})
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

    def icon_image() -> "Image.Image":
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=(150, 90, 220))
        return img

    cache = {"status": _fetch_status(socket)}

    def refresh() -> None:
        cache["status"] = _fetch_status(socket)

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
                out.append(pystray.MenuItem(it["text"], lambda ic, item: ic.stop()))
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

    icon = pystray.Icon("pana", icon_image(), "pana", menu=build())

    def poller() -> None:
        while True:
            time.sleep(5)
            try:
                rebuild(icon)
            except Exception:
                pass

    threading.Thread(target=poller, daemon=True).start()
    icon.run()


def main() -> None:
    parser = argparse.ArgumentParser(prog="pana-tray")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    run(parser.parse_args().socket)
