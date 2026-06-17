import asyncio

from pana.ipc.client import call
from pana.ipc.protocol import Request, Response
from pana.ipc.server import Server


def test_roundtrip(tmp_path):
    sock = str(tmp_path / "t.sock")

    async def handler(req: Request) -> Response:
        return Response(ok=True, data={"echo": req.cmd})

    async def body() -> Response:
        srv = Server(sock, handler)
        await srv.start()
        try:
            return await call(sock, Request(cmd="ping"))
        finally:
            await srv.stop()

    resp = asyncio.run(body())
    assert resp.ok is True
    assert resp.data["echo"] == "ping"


def test_malformed_request_does_not_crash(tmp_path):
    sock = str(tmp_path / "t.sock")

    async def handler(req: Request) -> Response:
        return Response(ok=True)

    async def body() -> bytes:
        srv = Server(sock, handler)
        await srv.start()
        try:
            reader, writer = await asyncio.open_unix_connection(path=sock)
            writer.write(b"not-json\n")
            await writer.drain()
            raw = await reader.readline()
            writer.close()
            return raw
        finally:
            await srv.stop()

    resp = Response.from_json(asyncio.run(body()).decode())
    assert resp.ok is False
    assert resp.error


def test_non_utf8_returns_error_and_keeps_connection(tmp_path):
    sock = str(tmp_path / "t.sock")

    async def handler(req: Request) -> Response:
        return Response(ok=True, data={"echo": req.cmd})

    async def body():
        srv = Server(sock, handler)
        await srv.start()
        try:
            reader, writer = await asyncio.open_unix_connection(path=sock)
            writer.write(b"\xff\xfe not utf8\n")
            await writer.drain()
            r1 = await reader.readline()
            # connection must survive: a valid request after the bad bytes still works
            writer.write((Request(cmd="ping").to_json() + "\n").encode())
            await writer.drain()
            r2 = await reader.readline()
            writer.close()
            return r1, r2
        finally:
            await srv.stop()

    r1, r2 = asyncio.run(body())
    assert Response.from_json(r1.decode()).ok is False
    assert Response.from_json(r2.decode()).data["echo"] == "ping"
