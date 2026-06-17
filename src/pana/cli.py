from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .ipc.client import call
from .ipc.protocol import Request

DEFAULT_SOCKET = "/run/pana/pana.sock"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pana")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    sub.add_parser("status")
    args = parser.parse_args(argv)

    resp = asyncio.run(call(args.socket, Request(cmd=args.cmd)))
    if not resp.ok:
        print(f"error: {resp.error}", file=sys.stderr)
        return 1
    print(json.dumps(resp.data, indent=2))
    return 0
