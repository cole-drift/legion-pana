# pana — Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the project skeleton and the language-agnostic spine — a root daemon (`panad`) that detects hardware capabilities and answers commands over a Unix-socket JSON protocol, plus a thin CLI (`pana`) that drives it — all fully tested against fake hardware.

**Architecture:** A privileged daemon owns hardware access through a swappable transport interface (real sysfs in production, a fake in tests). Clients are thin and speak a versioned newline-JSON protocol over a Unix domain socket — the protocol is the seam a future Rust port replaces. This phase ships the transport, capability detection, protocol, socket server/client, daemon wiring for `ping`/`status`, and the CLI skeleton. No hardware writes yet.

**Tech Stack:** Python 3.12 (Ubuntu 24.04), **standard library only** this phase (`asyncio`, `json`, `argparse`, `dataclasses`, `fnmatch`, `glob`, `pathlib`), `pytest` for tests, `src/` layout with `setuptools`.

## Global Constraints

- Python `>=3.12`; standard-library-only for Phase 1 (no third-party runtime deps).
- Package name `pana`; daemon entry `panad` (`pana.daemon:main`); CLI entry `pana` (`pana.cli:main`).
- Default socket path `/run/pana/pana.sock`; every socket path is a parameter (tests pass a temp path). Never hardcode the path inside logic.
- Wire protocol: newline-delimited JSON, one object per line; every message carries an integer `version` field (`PROTOCOL_VERSION = 1`); plain JSON only (no Python-specific framing) so a Rust daemon is a drop-in.
- All hardware access goes through the `Sysfs` transport interface — never call `pathlib`/`open` on `/sys` directly outside `hw/transport.py`. This is what makes everything testable and the Rust seam clean.
- The daemon must never crash on bad input: a malformed request returns `Response(ok=False, error=...)`, it does not raise out of the connection handler.
- TDD throughout: failing test first, minimal implementation, frequent commits.

---

## File Structure (Phase 1)

- `pyproject.toml` — project metadata, entry points, pytest config.
- `src/pana/__init__.py` — package marker + version.
- `src/pana/hw/__init__.py`
- `src/pana/hw/transport.py` — `Sysfs` interface, `RealSysfs`, `FakeSysfs`.
- `src/pana/hw/detect.py` — `Capabilities` dataclass + `detect(fs)`.
- `src/pana/ipc/__init__.py`
- `src/pana/ipc/protocol.py` — `Request`, `Response`, `PROTOCOL_VERSION`.
- `src/pana/ipc/server.py` — asyncio `Server`.
- `src/pana/ipc/client.py` — `call(socket_path, request)`.
- `src/pana/daemon.py` — `Daemon` wiring + `main()`.
- `src/pana/cli.py` — argparse skeleton + `main()`.
- `tests/` — mirrors the package.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/pana/__init__.py`
- Create: `src/pana/hw/__init__.py`
- Create: `src/pana/ipc/__init__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an importable `pana` package (`pana.__version__: str`); a working `pytest` invocation.

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import pana
    assert isinstance(pana.__version__, str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/FunStuff/legion-pana && python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pana'`.

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:
```toml
[project]
name = "pana"
version = "0.1.0"
description = "Lenovo Legion 7 16IAX10 control + monitoring tool"
requires-python = ">=3.12"

[project.scripts]
pana = "pana.cli:main"
panad = "pana.daemon:main"

[project.optional-dependencies]
dev = ["pytest>=7"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

One-time dev environment setup (do this before Step 2):
```bash
cd ~/FunStuff/legion-pana
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"   # installs pytest>=7 (needed for the pythonpath ini option)
```

`src/pana/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/pana/hw/__init__.py`: (empty file)

`src/pana/ipc/__init__.py`: (empty file)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: PASS. (`pythonpath = ["src"]` lets pytest import `pana` without an install.)

- [ ] **Step 5: Commit**

```bash
cd ~/FunStuff/legion-pana
git add pyproject.toml src/pana/__init__.py src/pana/hw/__init__.py src/pana/ipc/__init__.py tests/test_smoke.py
git commit -m "chore: project scaffold (src layout, pytest, entry points)"
```

---

### Task 2: Sysfs transport (real + fake)

**Files:**
- Create: `src/pana/hw/transport.py`
- Test: `tests/hw/test_transport.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Sysfs` — a `typing.Protocol` with `read(path: str) -> str`, `write(path: str, value: str) -> None`, `exists(path: str) -> bool`, `glob(pattern: str) -> list[str]`.
  - `RealSysfs()` — backed by the real filesystem.
  - `FakeSysfs(files: dict[str, str])` — in-memory; records writes in `.writes: list[tuple[str, str]]`; `read`/`write` of an absent path raise `FileNotFoundError`; `glob` uses `fnmatch` over keys and returns sorted matches.

- [ ] **Step 1: Write the failing test**

`tests/hw/__init__.py`: (empty file)

`tests/hw/test_transport.py`:
```python
import pytest
from pana.hw.transport import FakeSysfs


def test_read_strips_whitespace():
    fs = FakeSysfs({"/sys/x": "performance\n"})
    assert fs.read("/sys/x") == "performance"


def test_read_missing_raises():
    fs = FakeSysfs({})
    with pytest.raises(FileNotFoundError):
        fs.read("/sys/nope")


def test_write_records_and_updates():
    fs = FakeSysfs({"/sys/x": "0"})
    fs.write("/sys/x", "1")
    assert fs.read("/sys/x") == "1"
    assert fs.writes == [("/sys/x", "1")]


def test_write_missing_raises():
    fs = FakeSysfs({})
    with pytest.raises(FileNotFoundError):
        fs.write("/sys/nope", "1")


def test_exists():
    fs = FakeSysfs({"/sys/x": "1"})
    assert fs.exists("/sys/x") is True
    assert fs.exists("/sys/y") is False


def test_glob_matches_sorted():
    fs = FakeSysfs({
        "/a/ppt_pl1_spl/current_value": "70",
        "/a/ppt_pl2_sppt/current_value": "125",
        "/a/ppt_pl1_spl/min_value": "50",
    })
    assert fs.glob("/a/ppt_*/current_value") == [
        "/a/ppt_pl1_spl/current_value",
        "/a/ppt_pl2_sppt/current_value",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/hw/test_transport.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pana.hw.transport'`.

- [ ] **Step 3: Write minimal implementation**

`src/pana/hw/transport.py`:
```python
from __future__ import annotations

import fnmatch
import glob as _glob
from pathlib import Path
from typing import Protocol


class Sysfs(Protocol):
    def read(self, path: str) -> str: ...
    def write(self, path: str, value: str) -> None: ...
    def exists(self, path: str) -> bool: ...
    def glob(self, pattern: str) -> list[str]: ...


class RealSysfs:
    def read(self, path: str) -> str:
        return Path(path).read_text().strip()

    def write(self, path: str, value: str) -> None:
        Path(path).write_text(value)

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def glob(self, pattern: str) -> list[str]:
        return sorted(_glob.glob(pattern))


class FakeSysfs:
    def __init__(self, files: dict[str, str]):
        self._files = dict(files)
        self.writes: list[tuple[str, str]] = []

    def read(self, path: str) -> str:
        if path not in self._files:
            raise FileNotFoundError(path)
        return self._files[path].strip()

    def write(self, path: str, value: str) -> None:
        if path not in self._files:
            raise FileNotFoundError(path)
        self._files[path] = value
        self.writes.append((path, value))

    def exists(self, path: str) -> bool:
        return path in self._files

    def glob(self, pattern: str) -> list[str]:
        return sorted(p for p in self._files if fnmatch.fnmatch(p, pattern))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/hw/test_transport.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pana/hw/transport.py tests/hw/__init__.py tests/hw/test_transport.py
git commit -m "feat(hw): sysfs transport interface with real + fake backends"
```

---

### Task 3: Capability detection

**Files:**
- Create: `src/pana/hw/detect.py`
- Test: `tests/hw/test_detect.py`

**Interfaces:**
- Consumes: `pana.hw.transport.Sysfs`.
- Produces:
  - Module-level path constants: `PLATFORM_PROFILE`, `PLATFORM_PROFILE_CHOICES`, `PPT_DIR`, `CONSERVATION`, `CHARGE_TYPES`.
  - `Capabilities` dataclass with fields `power_modes: bool`, `profile_choices: list[str]`, `ppt: bool`, `ppt_attrs: list[str]`, `battery_conservation: bool`, and method `to_dict() -> dict`.
  - `detect(fs: Sysfs) -> Capabilities`.

- [ ] **Step 1: Write the failing test**

`tests/hw/test_detect.py`:
```python
from pana.hw import detect as d
from pana.hw.transport import FakeSysfs


def _legion_tree() -> FakeSysfs:
    return FakeSysfs({
        d.PLATFORM_PROFILE: "performance",
        d.PLATFORM_PROFILE_CHOICES: "low-power balanced balanced-performance performance custom",
        f"{d.PPT_DIR}/ppt_pl1_spl/current_value": "0",
        f"{d.PPT_DIR}/ppt_pl2_sppt/current_value": "0",
        f"{d.PPT_DIR}/ppt_pl3_fppt/current_value": "0",
        d.CONSERVATION: "0",
    })


def test_detect_on_legion():
    caps = d.detect(_legion_tree())
    assert caps.power_modes is True
    assert "custom" in caps.profile_choices
    assert caps.ppt is True
    assert caps.ppt_attrs == ["ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"]
    assert caps.battery_conservation is True


def test_detect_on_empty_machine():
    caps = d.detect(FakeSysfs({}))
    assert caps.power_modes is False
    assert caps.profile_choices == []
    assert caps.ppt is False
    assert caps.ppt_attrs == []
    assert caps.battery_conservation is False


def test_battery_detected_via_charge_types_only():
    caps = d.detect(FakeSysfs({d.CHARGE_TYPES: "[Standard] Long_Life"}))
    assert caps.battery_conservation is True


def test_to_dict_is_json_safe():
    import json
    caps = d.detect(_legion_tree())
    json.dumps(caps.to_dict())  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/hw/test_detect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pana.hw.detect'`.

- [ ] **Step 3: Write minimal implementation**

`src/pana/hw/detect.py`:
```python
from __future__ import annotations

from dataclasses import asdict, dataclass

from .transport import Sysfs

PLATFORM_PROFILE = "/sys/firmware/acpi/platform_profile"
PLATFORM_PROFILE_CHOICES = "/sys/firmware/acpi/platform_profile_choices"
PPT_DIR = "/sys/class/firmware-attributes/lenovo-wmi-other-0/attributes"
CONSERVATION = "/sys/bus/platform/devices/VPC2004:00/conservation_mode"
CHARGE_TYPES = "/sys/class/power_supply/BAT0/charge_types"


@dataclass
class Capabilities:
    power_modes: bool
    profile_choices: list[str]
    ppt: bool
    ppt_attrs: list[str]
    battery_conservation: bool

    def to_dict(self) -> dict:
        return asdict(self)


def detect(fs: Sysfs) -> Capabilities:
    power_modes = fs.exists(PLATFORM_PROFILE)
    choices: list[str] = []
    if fs.exists(PLATFORM_PROFILE_CHOICES):
        choices = fs.read(PLATFORM_PROFILE_CHOICES).split()
    ppt_attrs = [p.split("/")[-2] for p in fs.glob(f"{PPT_DIR}/ppt_*/current_value")]
    battery = fs.exists(CONSERVATION) or fs.exists(CHARGE_TYPES)
    return Capabilities(
        power_modes=power_modes,
        profile_choices=choices,
        ppt=bool(ppt_attrs),
        ppt_attrs=ppt_attrs,
        battery_conservation=battery,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/hw/test_detect.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pana/hw/detect.py tests/hw/test_detect.py
git commit -m "feat(hw): runtime capability detection over the sysfs transport"
```

---

### Task 4: Wire protocol

**Files:**
- Create: `src/pana/ipc/protocol.py`
- Test: `tests/ipc/test_protocol.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `PROTOCOL_VERSION: int = 1`.
  - `Request(cmd: str, args: dict = {}, version: int = PROTOCOL_VERSION)` with `to_json() -> str` and static `from_json(line: str) -> Request`.
  - `Response(ok: bool, data: dict = {}, error: str | None = None, version: int = PROTOCOL_VERSION)` with `to_json() -> str` and static `from_json(line: str) -> Response`.
  - JSON shape: request `{"version", "cmd", "args"}`; response `{"version", "ok", "data", "error"}`.

- [ ] **Step 1: Write the failing test**

`tests/ipc/__init__.py`: (empty file)

`tests/ipc/test_protocol.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ipc/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pana.ipc.protocol'`.

- [ ] **Step 3: Write minimal implementation**

`src/pana/ipc/protocol.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ipc/test_protocol.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pana/ipc/protocol.py tests/ipc/__init__.py tests/ipc/test_protocol.py
git commit -m "feat(ipc): versioned newline-JSON request/response protocol"
```

---

### Task 5: Socket server + client

**Files:**
- Create: `src/pana/ipc/server.py`
- Create: `src/pana/ipc/client.py`
- Test: `tests/ipc/test_socket.py`

**Interfaces:**
- Consumes: `pana.ipc.protocol.Request`, `pana.ipc.protocol.Response`.
- Produces:
  - `Handler = Callable[[Request], Awaitable[Response]]`.
  - `Server(socket_path: str, handler: Handler)` with `async start()`, `async stop()`, `async serve_forever()`. On a malformed line the handler is bypassed and `Response(ok=False, error=...)` is returned; the connection is not torn down by the error.
  - `async call(socket_path: str, req: Request) -> Response` in `client.py`.

- [ ] **Step 1: Write the failing test**

`tests/ipc/test_socket.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ipc/test_socket.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pana.ipc.server'`.

- [ ] **Step 3: Write minimal implementation**

`src/pana/ipc/server.py`:
```python
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
                line = raw.decode().strip()
                if not line:
                    continue
                try:
                    resp = await self.handler(Request.from_json(line))
                except Exception as exc:  # bad request must not kill the connection
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
```

`src/pana/ipc/client.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ipc/test_socket.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pana/ipc/server.py src/pana/ipc/client.py tests/ipc/test_socket.py
git commit -m "feat(ipc): asyncio unix-socket server + client with fail-soft requests"
```

---

### Task 6: Daemon wiring (`ping` / `status`)

**Files:**
- Create: `src/pana/daemon.py`
- Test: `tests/test_daemon.py`

**Interfaces:**
- Consumes: `pana.hw.transport.{RealSysfs, Sysfs}`, `pana.hw.detect.detect`, `pana.ipc.protocol.{Request, Response}`, `pana.ipc.server.Server`.
- Produces:
  - `DEFAULT_SOCKET: str = "/run/pana/pana.sock"`.
  - `Daemon(fs: Sysfs | None = None, socket_path: str = DEFAULT_SOCKET)` with attribute `caps: Capabilities` and coroutine `handle(req: Request) -> Response` (commands: `ping` → `{"pong": True}`; `status` → `{"capabilities": <dict>}`; anything else → `ok=False`), and coroutine `run()`.
  - `main()` — argparse (`--socket`), runs `Daemon(...).run()`.

- [ ] **Step 1: Write the failing test**

`tests/test_daemon.py`:
```python
import asyncio

from pana.daemon import Daemon
from pana.hw import detect as d
from pana.hw.transport import FakeSysfs
from pana.ipc.protocol import Request


def _daemon() -> Daemon:
    fs = FakeSysfs({
        d.PLATFORM_PROFILE: "performance",
        d.PLATFORM_PROFILE_CHOICES: "low-power balanced performance custom",
        d.CONSERVATION: "0",
    })
    return Daemon(fs=fs, socket_path="/tmp/unused.sock")


def test_ping():
    resp = asyncio.run(_daemon().handle(Request(cmd="ping")))
    assert resp.ok is True
    assert resp.data["pong"] is True


def test_status_returns_capabilities():
    resp = asyncio.run(_daemon().handle(Request(cmd="status")))
    assert resp.ok is True
    assert resp.data["capabilities"]["power_modes"] is True
    assert "custom" in resp.data["capabilities"]["profile_choices"]


def test_unknown_command():
    resp = asyncio.run(_daemon().handle(Request(cmd="frobnicate")))
    assert resp.ok is False
    assert "unknown" in resp.error.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_daemon.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pana.daemon'`.

- [ ] **Step 3: Write minimal implementation**

`src/pana/daemon.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_daemon.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pana/daemon.py tests/test_daemon.py
git commit -m "feat(daemon): minimal daemon wiring with ping/status over the socket"
```

---

### Task 7: CLI skeleton (`pana ping` / `pana status`)

**Files:**
- Create: `src/pana/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `pana.ipc.protocol.Request`, `pana.ipc.client.call` (imported as `pana.cli.call` so tests can monkeypatch it).
- Produces:
  - `main(argv: list[str] | None = None) -> int` — argparse with `--socket` (default `DEFAULT_SOCKET`) and subcommands `ping`, `status`. On `ok` prints `data` as indented JSON to stdout and returns `0`; on error prints `error: <msg>` to stderr and returns `1`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pana.cli'`.

- [ ] **Step 3: Write minimal implementation**

`src/pana/cli.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pana/cli.py tests/test_cli.py
git commit -m "feat(cli): pana CLI skeleton with ping/status over the socket"
```

---

### Task 8: Full-suite green + live smoke check

**Files:** none (verification task).

**Interfaces:** none.

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest -v`
Expected: PASS — all tests from Tasks 1–7 green (23 tests: 1 smoke + 6 transport + 4 detect + 5 protocol + 2 socket + 3 daemon + 2 cli).

- [ ] **Step 2: Live smoke test against real hardware (read-only)**

This is the one place we touch the real machine, and it is strictly read-only (capability detection just stats/reads sysfs).

```bash
cd ~/FunStuff/legion-pana
# editable install so the entry points exist
pip install -e .
# start the daemon on a user-writable socket (no root needed for read-only detect)
panad --socket /tmp/pana-smoke.sock &
sleep 1
pana --socket /tmp/pana-smoke.sock status
kill %1
```
Expected: JSON showing `"power_modes": true`, `profile_choices` including `custom`, `"ppt": true`, `ppt_attrs` listing `ppt_pl1_spl`/`ppt_pl2_sppt`/`ppt_pl3_fppt`, `"battery_conservation": true`. This confirms the real `RealSysfs` paths match this machine.

- [ ] **Step 3: Commit any path corrections**

If a constant in `detect.py` was wrong for the live machine, fix it, re-run `python -m pytest -v`, then:
```bash
git add -A
git commit -m "fix(hw): correct sysfs path constants against live 16IAX10"
```

---

## Phase Roadmap (subsequent plans, written just-in-time)

Each subsequent phase gets its own detailed TDD plan, written after the prior phase's hardware verification informs it. Each produces working, testable software on its own.

- **Phase 2 — Thermal & presets:** `hw/platform_profile.py`, `hw/ppt.py` (custom-mode sequencing + 50–110 / 60–168 clamping), `core/presets.py` (Eco/Balanced/Game/Custom), `core/config.py` (TOML + corrupt-recovery), `core/state.py` (re-apply on boot/resume/power-change), daemon commands + `pana mode`/`pana tdp`. **Gated by:** live confirmation that `custom` + ppt writes change RAPL package power (spec §9.2).
- **Phase 3 — Battery:** `hw/battery.py` (conservation toggle + capacity/status), `core/battery_watch.py` (soft-target hysteresis/debounce), `pana battery`. **Gated by:** measuring the firmware cap % (spec §9.1).
- **Phase 4 — Lights:** `hw/lights.py` (Spectrum HID transport + empirical device discovery `0xCD`/`0xC4`, brightness/off, best-effort static color), `core/scheduler.py` (night schedule), `pana lights`/`pana night`. **Gated by:** identifying which of `c197`/`c193` drives the keyboard (spec §9.3–§9.4).
- **Phase 5 — Monitoring:** `hw/sensors.py` (coretemp / nvme / RAPL-delta / battery / cpufreq / optional nvidia-smi), `core/monitor.py` (sampler + rolling history + subscribe/stream), `pana monitor`, optional usage log.
- **Phase 6 — Tray & packaging:** `pana/tray.py` (pystray/PyQt6, waits for the StatusNotifierWatcher), `packaging/panad.service` (hardened, `ReadWritePaths`), user `pana-tray.service`, udev rules (hidraw `uaccess` for `048d:c193`/`c197`; `power_supply` re-apply), install `Makefile`, and `docs/PROTOCOL.md`. **Note:** requires `apt install gnome-shell-extension-appindicator` on Ubuntu 24.04 GNOME for the tray to appear.
