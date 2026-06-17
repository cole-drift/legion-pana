from __future__ import annotations

import json
from dataclasses import dataclass, field

PROTOCOL_VERSION = 1


@dataclass
class Request:
    cmd: str
    args: dict = field(default_factory=dict)
    version: int = PROTOCOL_VERSION

    def to_json(self) -> str:
        return json.dumps({"version": self.version, "cmd": self.cmd, "args": self.args})

    @staticmethod
    def from_json(line: str) -> "Request":
        d = json.loads(line)
        return Request(
            cmd=d["cmd"],
            args=d.get("args", {}),
            version=d.get("version", PROTOCOL_VERSION),
        )


@dataclass
class Response:
    ok: bool
    data: dict = field(default_factory=dict)
    error: str | None = None
    version: int = PROTOCOL_VERSION

    def to_json(self) -> str:
        return json.dumps(
            {"version": self.version, "ok": self.ok, "data": self.data, "error": self.error}
        )

    @staticmethod
    def from_json(line: str) -> "Response":
        d = json.loads(line)
        return Response(
            ok=d["ok"],
            data=d.get("data", {}),
            error=d.get("error"),
            version=d.get("version", PROTOCOL_VERSION),
        )
