from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable

from .protocol import Request, Response

Handler = Callable[[Request], Awaitable[Response]]


class Server:
    def __init__(self, socket_path: str, handler: Handler):
        self.socket_path = socket_path
        self.handler = handler
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self._server = await asyncio.start_unix_server(self._on_client, path=self.socket_path)

    async def _on_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            async for raw in reader:
                try:
                    line = raw.decode().strip()  # bad bytes / bad json must not drop the conn
                    if not line:
                        continue
                    resp = await self.handler(Request.from_json(line))
                except Exception as exc:
                    resp = Response(ok=False, error=str(exc))
                writer.write((resp.to_json() + "\n").encode())
                await writer.drain()
        finally:
            writer.close()

    async def serve_forever(self) -> None:
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
