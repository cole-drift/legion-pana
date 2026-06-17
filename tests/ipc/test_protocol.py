import json

from pana.ipc.protocol import PROTOCOL_VERSION, Request, Response


def test_request_roundtrip():
    req = Request(cmd="mode", args={"name": "eco"})
    back = Request.from_json(req.to_json())
    assert back.cmd == "mode"
    assert back.args == {"name": "eco"}
    assert back.version == PROTOCOL_VERSION


def test_request_defaults_args_and_version():
    req = Request.from_json(json.dumps({"cmd": "status"}))
    assert req.args == {}
    assert req.version == PROTOCOL_VERSION


def test_request_emits_version_field():
    assert json.loads(Request(cmd="ping").to_json())["version"] == PROTOCOL_VERSION


def test_response_roundtrip_ok():
    resp = Response(ok=True, data={"pong": True})
    back = Response.from_json(resp.to_json())
    assert back.ok is True
    assert back.data == {"pong": True}
    assert back.error is None


def test_response_roundtrip_error():
    back = Response.from_json(Response(ok=False, error="boom").to_json())
    assert back.ok is False
    assert back.error == "boom"
