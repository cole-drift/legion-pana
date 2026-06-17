from __future__ import annotations

import array
import fcntl
import os
from typing import Protocol


class HidTransport(Protocol):
    def send_feature(self, data: bytes) -> None: ...
    def get_feature(self, size: int, report_id: int) -> bytes: ...


def _hidiocsfeature(size: int) -> int:
    return 0xC0004806 | (size << 16)


def _hidiocgfeature(size: int) -> int:
    return 0xC0004807 | (size << 16)


class RealHid:
    """hidraw-backed transport (HIDIOCSFEATURE/HIDIOCGFEATURE); no kernel detach."""

    def __init__(self, path: str):
        self._fd = os.open(path, os.O_RDWR)

    def send_feature(self, data: bytes) -> None:
        buf = array.array("B", data)
        fcntl.ioctl(self._fd, _hidiocsfeature(len(buf)), buf, True)

    def get_feature(self, size: int, report_id: int) -> bytes:
        buf = array.array("B", [0] * size)
        buf[0] = report_id
        fcntl.ioctl(self._fd, _hidiocgfeature(size), buf, True)
        return bytes(buf)

    def close(self) -> None:
        os.close(self._fd)


class FakeHid:
    """In-memory transport for tests. Records sent reports; replies via op map."""

    def __init__(self, get_responses: dict[int, bytes] | None = None):
        self.sent: list[bytes] = []
        self._get_responses = get_responses or {}

    def send_feature(self, data: bytes) -> None:
        self.sent.append(bytes(data))

    def get_feature(self, size: int, report_id: int) -> bytes:
        op = self.sent[-1][1] if self.sent else None
        resp = self._get_responses.get(op, bytes([report_id]))
        return resp.ljust(size, b"\x00")
