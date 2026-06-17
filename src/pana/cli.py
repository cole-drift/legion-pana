from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from .ipc.client import call
from .ipc.protocol import Request

DEFAULT_SOCKET = "/run/pana/pana.sock"


def _hex_to_rgb(s: str) -> list[int]:
    s = s.lstrip("#")
    if len(s) != 6:
        raise SystemExit("color must be RRGGBB hex")
    return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)]


def _build_request(args: argparse.Namespace) -> Request:
    c = args.cmd
    if c in ("ping", "status", "reapply"):
        return Request(cmd=c)
    if c == "mode":
        return Request(cmd="mode", args={"name": args.name})
    if c == "power":
        return Request(cmd="power", args={"pct": args.pct})
    if c == "battery":
        if args.off:
            return Request(cmd="battery", args={"off": True})
        if args.cap:
            return Request(cmd="battery", args={"cap": True})
        return Request(cmd="battery", args={"target": args.limit})
    if c == "lights":
        a = {}
        if args.state == "on":
            a["on"] = True
        elif args.state == "off":
            a["on"] = False
        if args.brightness is not None:
            a["brightness"] = args.brightness
        if args.color:
            a["color"] = _hex_to_rgb(args.color)
        if args.effect:
            a["effect"] = args.effect
        if args.zone:
            a["zone"] = args.zone
        if args.logo:
            a["logo"] = args.logo == "on"
        if not a:
            raise SystemExit("lights needs on|off|--brightness|--color|--effect|--zone|--logo")
        return Request(cmd="lights", args=a)
    if c == "night":
        a = {}
        if args.state == "clear":
            a["clear"] = True
        elif args.state == "on":
            a["enabled"] = True
        elif args.state == "off":
            a["enabled"] = False
        if args.start:
            a["start"] = args.start
        if args.end:
            a["end"] = args.end
        if not a:
            raise SystemExit("night needs on|off|clear and/or --start HH:MM --end HH:MM")
        return Request(cmd="night", args=a)
    raise SystemExit(f"unhandled command {c}")


def _fmt_monitor(s: dict) -> str:
    bat = s.get("battery") or {}
    power = s.get("cpu_power_w")
    temp = s.get("cpu_temp_c")
    return (
        f"CPU {power if power is not None else '?'}W "
        f"{temp if temp is not None else '?'}°C | "
        f"bat {bat.get('capacity')}% {bat.get('status')} {bat.get('power_w')}W | "
        f"{'AC' if s.get('ac_online') else 'DC'}"
    )


def _monitor_loop(socket: str, interval: float) -> int:
    try:
        while True:
            resp = asyncio.run(call(socket, Request(cmd="monitor")))
            if not resp.ok:
                print(f"error: {resp.error}", file=sys.stderr)
                return 1
            sample = resp.data.get("sample")
            print(_fmt_monitor(sample) if sample else "(warming up...)")
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pana", description="Legion 7 16IAX10 control + monitoring")
    p.add_argument("--socket", default=DEFAULT_SOCKET)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    sub.add_parser("status")
    sub.add_parser("reapply")
    mon = sub.add_parser("monitor")
    mon.add_argument("--interval", type=float, default=2.0)
    m = sub.add_parser("mode")
    m.add_argument("name", help="eco | balanced | game | <custom preset>")
    pw = sub.add_parser("power", help="custom CPU clock-ceiling cap")
    pw.add_argument("pct", type=int, help="max CPU performance %% (10-100); lower = cooler")
    b = sub.add_parser("battery")
    bg = b.add_mutually_exclusive_group(required=True)
    bg.add_argument("--cap", action="store_true", help="enable firmware conservation cap")
    bg.add_argument("--limit", type=int, help="soft target %% (held at/above the firmware cap)")
    bg.add_argument("--off", action="store_true", help="charge to 100%%")
    li = sub.add_parser("lights")
    li.add_argument("state", nargs="?", choices=["on", "off"])
    li.add_argument("--brightness", type=int, help="0-9")
    li.add_argument("--color", help="RRGGBB hex (solid color); 000000 turns a zone off")
    li.add_argument("--effect", choices=["static", "rainbow", "breathe"])
    li.add_argument("--zone", choices=["keyboard", "perimeter", "rear", "logo", "all"],
                    help="which LEDs --color/--effect apply to (rear = strip above keyboard)")
    li.add_argument("--logo", choices=["on", "off"], help="lid LEGION logo on/off")
    n = sub.add_parser("night")
    n.add_argument("state", nargs="?", choices=["on", "off", "clear"])
    n.add_argument("--start", help="night-window start HH:MM (e.g. 21:30)")
    n.add_argument("--end", help="night-window end HH:MM (e.g. 06:30)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.cmd == "monitor":
        return _monitor_loop(args.socket, args.interval)
    resp = asyncio.run(call(args.socket, _build_request(args)))
    if not resp.ok:
        print(f"error: {resp.error}", file=sys.stderr)
        return 1
    print(json.dumps(resp.data, indent=2))
    return 0
