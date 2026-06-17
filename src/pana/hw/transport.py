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
