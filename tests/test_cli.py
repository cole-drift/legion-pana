import json

import pytest

import pana.cli as cli
from pana.ipc.protocol import Response


def _capture_request(monkeypatch):
    """Patch cli.call to capture the Request and return an ok Response."""
    captured = {}

    async def fake_call(socket_path, req):
        captured["socket"] = socket_path
        captured["req"] = req
        return Response(ok=True, data={"echoed": req.args})

    monkeypatch.setattr(cli, "call", fake_call)
    return captured


def test_status_prints_data(monkeypatch, capsys):
    cap = _capture_request(monkeypatch)
    assert cli.main(["status"]) == 0
    assert cap["req"].cmd == "status"
    json.loads(capsys.readouterr().out)  # valid JSON


def test_error_returns_1(monkeypatch, capsys):
    async def fake_call(socket_path, req):
        return Response(ok=False, error="daemon down")

    monkeypatch.setattr(cli, "call", fake_call)
    assert cli.main(["ping"]) == 1
    assert "daemon down" in capsys.readouterr().err


def test_mode_request(monkeypatch):
    cap = _capture_request(monkeypatch)
    cli.main(["mode", "eco"])
    assert cap["req"].cmd == "mode"
    assert cap["req"].args == {"name": "eco"}


def test_tdp_request(monkeypatch):
    cap = _capture_request(monkeypatch)
    cli.main(["tdp", "--pl1", "50", "--pl2", "60"])
    assert cap["req"].args == {"pl1": 50, "pl2": 60}


def test_battery_variants(monkeypatch):
    cap = _capture_request(monkeypatch)
    cli.main(["battery", "--limit", "85"])
    assert cap["req"].args == {"target": 85}
    cli.main(["battery", "--cap"])
    assert cap["req"].args == {"cap": True}
    cli.main(["battery", "--off"])
    assert cap["req"].args == {"off": True}


def test_battery_requires_a_choice(monkeypatch):
    _capture_request(monkeypatch)
    with pytest.raises(SystemExit):
        cli.main(["battery"])  # mutually-exclusive group is required


def test_lights_off_and_color(monkeypatch):
    cap = _capture_request(monkeypatch)
    cli.main(["lights", "off"])
    assert cap["req"].args == {"on": False}
    cli.main(["lights", "--color", "ff0080"])
    assert cap["req"].args == {"color": [255, 0, 128]}


def test_lights_needs_something(monkeypatch):
    _capture_request(monkeypatch)
    with pytest.raises(SystemExit):
        cli.main(["lights"])


def test_night_states(monkeypatch):
    cap = _capture_request(monkeypatch)
    cli.main(["night", "on"])
    assert cap["req"].args == {"enabled": True}
    cli.main(["night", "clear"])
    assert cap["req"].args == {"clear": True}


def test_fmt_monitor_line():
    line = cli._fmt_monitor({
        "cpu_power_w": 12.3, "cpu_temp_c": 52.0,
        "battery": {"capacity": 38, "status": "Charging", "power_w": 15.0},
        "ac_online": True,
    })
    assert "12.3W" in line and "52.0°C" in line and "38%" in line and "AC" in line
