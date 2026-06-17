from __future__ import annotations

import argparse
import asyncio

from .ipc.client import call
from .ipc.protocol import Request

DEFAULT_SOCKET = "/run/pana/pana.sock"
MODES = ["eco", "balanced", "game"]


def menu_model(status: dict) -> list[dict]:
    """Build a backend-agnostic menu description from a status snapshot.

    Pure + testable; the pystray glue in run() translates this to a real menu.
    """
    mode = status.get("mode")
    pp = status.get("platform_profile")
    bat = status.get("battery") or {}
    lights = status.get("lights") or {}

    items: list[dict] = [
        {"type": "label", "text": f"pana — {mode or '?'} / {pp or '?'}"},
        {"type": "label", "text": f"battery {bat.get('capacity')}% {bat.get('status') or ''}".strip()},
        {"type": "separator"},
    ]
    for m in MODES:
        items.append({"text": m.capitalize(), "cmd": "mode", "args": {"name": m}, "checked": mode == m})
    items.append({"type": "separator"})
    items.append({"text": "Lights off", "cmd": "lights", "args": {"on": False}})
    items.append({"text": "Lights on", "cmd": "lights", "args": {"on": True}})
    items.append({
        "text": "Battery cap",
        "cmd": "battery",
        "args": {"cap": True},
        "checked": bool(bat.get("conservation")),
    })
    items.append({"text": "Charge to 100%", "cmd": "battery", "args": {"off": True}})
    if not lights.get("available", True):
        items.append({"type": "label", "text": "(no lighting device)"})
    items.append({"type": "separator"})
    items.append({"text": "Quit", "action": "quit"})
    return items


def _send(socket: str, cmd: str, args: dict) -> dict:
    resp = asyncio.run(call(socket, Request(cmd=cmd, args=args)))
    return resp.data if resp.ok else {}


def _fetch_status(socket: str) -> dict:
    try:
        resp = asyncio.run(call(socket, Request(cmd="status")))
        return resp.data if resp.ok else {}
    except OSError:
        return {}


def run(socket: str = DEFAULT_SOCKET) -> None:  # pragma: no cover - GUI glue
    import pystray
    from PIL import Image, ImageDraw

    def icon_image() -> "Image.Image":
        img = Image.new("RGB", (64, 64), (24, 24, 28))
        dc = ImageDraw.Draw(img)
        dc.ellipse((14, 14, 50, 50), fill=(150, 90, 220))
        return img

    def build_menu():
        model = menu_model(_fetch_status(socket))
        entries = []
        for item in model:
            if item.get("type") == "separator":
                entries.append(pystray.Menu.SEPARATOR)
            elif item.get("type") == "label":
                entries.append(pystray.MenuItem(item["text"], None, enabled=False))
            elif item.get("action") == "quit":
                entries.append(pystray.MenuItem(item["text"], lambda icon, _: icon.stop()))
            else:
                cmd, args = item["cmd"], item["args"]
                entries.append(
                    pystray.MenuItem(
                        item["text"],
                        (lambda c, a: lambda icon, _: _send(socket, c, a))(cmd, args),
                        checked=(lambda it: lambda _i: it.get("checked"))(item)
                        if "checked" in item
                        else None,
                    )
                )
        return pystray.Menu(*entries)

    icon = pystray.Icon("pana", icon_image(), "pana", menu=build_menu())
    icon.run()


def main() -> None:
    parser = argparse.ArgumentParser(prog="pana-tray")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    run(parser.parse_args().socket)
