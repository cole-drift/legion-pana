from __future__ import annotations

import argparse
import asyncio

from .ipc.client import call
from .ipc.protocol import Request

DEFAULT_SOCKET = "/run/pana/pana.sock"
MODES = ["eco", "balanced", "game"]


def menu_model(status: dict) -> list[dict]:
    """Backend-agnostic menu description from a status snapshot (pure + testable).

    Fixed item set (order/length never varies with status) so a backend can build
    the items once and just re-read text/checked. Actionable items carry cmd/args.
    """
    mode = status.get("mode")
    bat = status.get("battery") or {}
    lights = status.get("lights") or {}
    mon = status.get("monitor") or {}
    cons = bat.get("conservation")

    cap = bat.get("capacity")
    temp = mon.get("cpu_temp_c")
    power = mon.get("cpu_power_w")
    title = f"pana — {mode or '?'} · {cap if cap is not None else '?'}%"
    if temp is not None:
        title += f" · {temp:g}°C"
    if power is not None:
        title += f" · {power:g}W"

    items: list[dict] = [
        {"type": "label", "text": title},
        {"type": "separator"},
        {"text": "Eco (cool & quiet)", "cmd": "mode", "args": {"name": "eco"},
         "checked": mode == "eco", "radio": True},
        {"text": "Balanced", "cmd": "mode", "args": {"name": "balanced"},
         "checked": mode == "balanced", "radio": True},
        {"text": "Game (full power)", "cmd": "mode", "args": {"name": "game"},
         "checked": mode == "game", "radio": True},
        {"type": "separator"},
        {"text": "Lights off", "cmd": "lights", "args": {"on": False}},
        {"text": "Lights on", "cmd": "lights", "args": {"on": True}},
        {"text": "Night schedule", "cmd": "night",
         "args": {"enabled": not bool(lights.get("night_enabled"))},
         "checked": bool(lights.get("night_enabled"))},
        {"type": "separator"},
        {"text": "Battery: conserve (~80%)", "cmd": "battery", "args": {"cap": True},
         "checked": cons is True, "radio": True},
        {"text": "Battery: full charge", "cmd": "battery", "args": {"off": True},
         "checked": cons is False, "radio": True},
        {"type": "separator"},
        {"text": "Refresh", "action": "refresh"},
        {"text": "Quit", "action": "quit"},
    ]
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

    import pystray
    from PIL import Image, ImageDraw

    def icon_image() -> "Image.Image":
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        dc = ImageDraw.Draw(img)
        dc.ellipse((8, 8, 56, 56), fill=(150, 90, 220))
        return img

    state = {"model": menu_model(_fetch_status(socket))}

    def rerender() -> None:
        state["model"] = menu_model(_fetch_status(socket))

    def text_cb(idx):
        return lambda item: state["model"][idx].get("text", "")

    def checked_cb(idx):
        return lambda item: bool(state["model"][idx].get("checked"))

    def action_cb(idx):
        def handler(icon, item):
            it = state["model"][idx]
            _send(socket, it["cmd"], it["args"])
            rerender()
            icon.update_menu()
        return handler

    entries = []
    for idx, it in enumerate(state["model"]):
        if it.get("type") == "separator":
            entries.append(pystray.Menu.SEPARATOR)
        elif it.get("type") == "label":
            entries.append(pystray.MenuItem(text_cb(idx), None, enabled=False))
        elif it.get("action") == "quit":
            entries.append(pystray.MenuItem(it["text"], lambda icon, item: icon.stop()))
        elif it.get("action") == "refresh":
            entries.append(pystray.MenuItem(
                it["text"], lambda icon, item: (rerender(), icon.update_menu())))
        else:
            entries.append(pystray.MenuItem(
                text_cb(idx), action_cb(idx),
                checked=checked_cb(idx) if "checked" in it else None,
                radio=it.get("radio", False)))

    icon = pystray.Icon("pana", icon_image(), "pana", menu=pystray.Menu(*entries))

    def poller() -> None:
        import time
        while True:
            time.sleep(5)
            rerender()
            try:
                icon.update_menu()
                s = state["model"][0]["text"]
                icon.title = s
            except Exception:
                pass

    threading.Thread(target=poller, daemon=True).start()
    icon.run()


def main() -> None:
    parser = argparse.ArgumentParser(prog="pana-tray")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    run(parser.parse_args().socket)
