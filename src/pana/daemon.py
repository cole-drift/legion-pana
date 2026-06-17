from __future__ import annotations

import argparse
import asyncio
import os
import signal
from datetime import datetime, time
from typing import Callable

from .core import scheduler
from .core.config import Config, State
from .core.battery_watch import BatteryWatcher
from .core.manager import Manager
from .core.monitor import Monitor
from .hw import detect as detect_mod
from .hw.hid import HidTransport
from .hw.transport import Sysfs
from .ipc.protocol import Request, Response
from .ipc.server import Server

DEFAULT_SOCKET = "/run/pana/pana.sock"


def _sd_notify(message: str) -> None:
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    try:
        import socket as _socket

        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        with _socket.socket(_socket.AF_UNIX, _socket.SOCK_DGRAM) as sock:
            sock.connect(addr)
            sock.sendall(message.encode())
    except OSError:
        pass


class Daemon:
    def __init__(
        self,
        fs: Sysfs | None = None,
        lights_opener: Callable[[str], HidTransport] | None = None,
        socket_path: str = DEFAULT_SOCKET,
        config: Config | None = None,
        state: State | None = None,
    ):
        cfg = config or Config.load()
        st = state if state is not None else State.load()
        self.manager = Manager(fs=fs, lights_opener=lights_opener, config=cfg, state=st)
        self.monitor = Monitor(self.manager.sensors)
        self.battery_watcher = BatteryWatcher(
            self.manager.battery,
            lambda: self.manager.state.battery_target,
            interval=cfg.poll_interval_s,
        )
        self.socket_path = socket_path
        self._stop = asyncio.Event()
        self._last_light_state: str | None = None
        self._last_ac: bool | None = None
        self._handlers: dict[str, Callable[[dict], dict]] = {
            "ping": lambda a: {"pong": True},
            "status": self._h_status,
            "reapply": lambda a: (self.manager.reapply(), self.manager.status())[1],
            "monitor": lambda a: {"sample": self.monitor.latest()},
            "mode": lambda a: self.manager.apply_mode(a["name"]),
            "tdp": lambda a: self.manager.set_tdp(a.get("pl1"), a.get("pl2")),
            "battery": lambda a: self.manager.set_battery(
                cap=a.get("cap", False), target=a.get("target"), off=a.get("off", False)
            ),
            "lights": lambda a: self.manager.set_lights(
                on=a.get("on"),
                brightness=a.get("brightness"),
                color=tuple(a["color"]) if a.get("color") else None,
            ),
            "night": lambda a: self.manager.set_night(
                enabled=a.get("enabled"), clear_manual=a.get("clear", False)
            ),
        }

    # ---- command handlers ----

    def _h_status(self, args: dict) -> dict:
        data = self.manager.status()
        data["monitor"] = self.monitor.latest()
        data["capabilities"] = detect_mod.detect(self.manager.fs).to_dict()
        return data

    async def handle(self, req: Request) -> Response:
        fn = self._handlers.get(req.cmd)
        if fn is None:
            return Response(ok=False, error=f"unknown command: {req.cmd}")
        try:
            return Response(ok=True, data=fn(req.args))
        except Exception as exc:
            return Response(ok=False, error=f"{type(exc).__name__}: {exc}")

    # ---- periodic work ----

    def _scheduler_tick(self, now_t: time | None = None) -> str | None:
        now_t = now_t or datetime.now().time()
        desired = scheduler.desired_lights(
            now_t,
            self.manager.night_enabled(),
            self.manager.config.night_start,
            self.manager.config.night_end,
            self.manager.state.lights_manual,
        )
        if desired is None or not self.manager.lights.available():
            return None
        if desired == self._last_light_state:
            return None
        try:
            if desired == "off":
                self.manager.lights.off()
            else:
                self.manager.lights.set_brightness(self.manager.config.light_on_brightness)
            self._last_light_state = desired
        except Exception:
            return None
        return desired

    def _check_power_transition(self) -> str | None:
        """On AC<->DC change, re-apply settings (the firmware resets TDP on transition)."""
        ac = self.manager.battery.ac_online()
        if ac is None or ac == self._last_ac:
            return None
        self._last_ac = ac
        auto = self.manager.config.auto_on_battery
        if auto and ac is False:
            self.manager.apply_mode(auto)
            return f"auto:{auto}"
        self.manager.reapply()
        return "reapply"

    def _monitor_tick(self) -> None:
        self.monitor.sample()
        try:
            self._check_power_transition()
        except Exception:
            pass

    async def _every(self, interval: float, fn: Callable[[], None]) -> None:
        while not self._stop.is_set():
            try:
                fn()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    def _secure_socket(self) -> None:
        try:
            os.chmod(self.socket_path, 0o660)
        except OSError:
            pass
        group = os.environ.get("PANA_SOCKET_GROUP")
        if group:
            try:
                import grp

                os.chown(self.socket_path, -1, grp.getgrnam(group).gr_gid)
            except (OSError, KeyError):
                pass

    async def run(self) -> None:
        self._stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except (NotImplementedError, ValueError):
                pass

        server = Server(self.socket_path, self.handle)
        await server.start()
        self._secure_socket()
        self.manager.reapply()
        _sd_notify("READY=1")

        tasks = [
            asyncio.create_task(server.serve_forever()),
            asyncio.create_task(self._every(self.manager.config.monitor_interval_s, self._monitor_tick)),
            asyncio.create_task(self.battery_watcher.run(self._stop)),
            asyncio.create_task(self._every(self.manager.config.poll_interval_s, self._scheduler_tick)),
        ]
        try:
            await self._stop.wait()
        finally:
            for t in tasks:
                t.cancel()
            await server.stop()


def main() -> None:
    parser = argparse.ArgumentParser(prog="panad")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    args = parser.parse_args()
    asyncio.run(Daemon(socket_path=args.socket).run())
