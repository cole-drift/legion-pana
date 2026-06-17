from __future__ import annotations

import asyncio

from .protocol import Request, Response


async def call(socket_path: str, req: Request) -> Response:
    reader, writer = await asyncio.open_unix_connection(path=socket_path)
    try:
        writer.write((req.to_json() + "\n").encode())
        await writer.drain()
        raw = await reader.readline()
        return Response.from_json(raw.decode())
    finally:
        writer.close()
