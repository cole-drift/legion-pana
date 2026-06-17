import json

import pana.cli as cli
from pana.ipc.protocol import Response


def test_status_prints_data(monkeypatch, capsys):
    async def fake_call(socket_path, req):
        assert req.cmd == "status"
        return Response(ok=True, data={"capabilities": {"power_modes": True}})

    monkeypatch.setattr(cli, "call", fake_call)
    rc = cli.main(["status"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["capabilities"]["power_modes"] is True


def test_error_returns_1(monkeypatch, capsys):
    async def fake_call(socket_path, req):
        return Response(ok=False, error="daemon down")

    monkeypatch.setattr(cli, "call", fake_call)
    rc = cli.main(["ping"])
    assert rc == 1
    assert "daemon down" in capsys.readouterr().err
