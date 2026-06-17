from __future__ import annotations

import argparse
import asyncio

from .hw import detect as detect_mod
from .hw.transport import RealSysfs, Sysfs
from .ipc.protocol import Request, Response
from .ipc.server import Server

DEFAULT_SOCKET = "/run/pana/pana.sock"


class Daemon:
    def __init__(self, fs: Sysfs | None = None, socket_path: str = DEFAULT_SOCKET):
        self.fs: Sysfs = fs or RealSysfs()
        self.socket_path = socket_path
        self.caps = detect_mod.detect(self.fs)

    async def handle(self, req: Request) -> Response:
        if req.cmd == "ping":
            return Response(ok=True, data={"pong": True})
        if req.cmd == "status":
            return Response(ok=True, data={"capabilities": self.caps.to_dict()})
        return Response(ok=False, error=f"unknown command: {req.cmd}")

    async def run(self) -> None:
        server = Server(self.socket_path, self.handle)
        await server.start()
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(prog="panad")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    args = parser.parse_args()
    asyncio.run(Daemon(socket_path=args.socket).run())
