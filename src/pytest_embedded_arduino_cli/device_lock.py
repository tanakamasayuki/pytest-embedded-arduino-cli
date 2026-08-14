from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sys

import portalocker


class DeviceLockError(TimeoutError):
    """Raised when a device lock cannot be acquired in time."""


def default_lock_dir() -> Path:
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            return Path(base) / "pytest-embedded-arduino-cli" / "locks"
        return Path.home() / "AppData" / "Local" / "pytest-embedded-arduino-cli" / "locks"

    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "pytest-embedded-arduino-cli" / "locks"

    cache_dir = os.getenv("XDG_CACHE_HOME")
    if cache_dir:
        return Path(cache_dir) / "pytest-embedded-arduino-cli" / "locks"

    return Path.home() / ".cache" / "pytest-embedded-arduino-cli" / "locks"


def normalize_device_key(key: str) -> str:
    """Resolve a device key to its underlying device node.

    ``/dev/serial/by-id/...`` and ``/dev/serial/by-path/...`` are symlinks to the
    real ``/dev/ttyUSB*`` node, so two runs naming the same device differently must
    still collide on the same lock. Keys that are not existing filesystem paths
    (``COM3``, arbitrary override labels) are returned unchanged.
    """
    if not key:
        return key
    try:
        if not os.path.exists(key):
            return key
        return os.path.realpath(key)
    except OSError:
        return key


def lock_file_name(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"device-{digest}.lock"


def read_lock_metadata(path: Path) -> dict[str, object] | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


@dataclass(frozen=True)
class DeviceLockInfo:
    key: str
    port: str | None = None
    profile: str | None = None
    sketch_dir: str | None = None
    role: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", normalize_device_key(self.key))


class DeviceLock:
    def __init__(
        self,
        info: DeviceLockInfo,
        *,
        lock_dir: Path | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.info = info
        self.lock_dir = lock_dir or default_lock_dir()
        self.timeout = timeout
        self.path = self.lock_dir / lock_file_name(info.key)
        self._lock: portalocker.Lock | None = None
        self._handle = None

    def acquire(self) -> None:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._lock = portalocker.Lock(
            self.path,
            mode="a+",
            timeout=self.timeout,
        )
        try:
            self._handle = self._lock.acquire()
        except portalocker.exceptions.LockException as e:
            metadata = read_lock_metadata(self.path)
            details = f"device lock timeout for {self.info.key!r}"
            if metadata:
                details = f"{details}; current metadata: {metadata}"
            raise DeviceLockError(details) from e

        metadata = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "key": self.info.key,
            "port": self.info.port,
            "profile": self.info.profile,
            "sketch_dir": self.info.sketch_dir,
            "role": self.info.role,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self._handle.seek(0)
        self._handle.truncate()
        json.dump(metadata, self._handle, sort_keys=True)
        self._handle.write("\n")
        self._handle.flush()

    def release(self) -> None:
        if self._lock is None:
            return
        try:
            self._lock.release()
        finally:
            self._lock = None
            self._handle = None


class DeviceLockSet:
    def __init__(
        self,
        infos: list[DeviceLockInfo],
        *,
        lock_dir: Path | None = None,
        timeout: float = 300.0,
    ) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for info in infos:
            if info.key in seen:
                duplicates.add(info.key)
            seen.add(info.key)
        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(f"duplicate device lock key: {duplicate_list}")

        self.locks = [
            DeviceLock(info, lock_dir=lock_dir, timeout=timeout)
            for info in sorted(infos, key=lambda item: item.key)
        ]

    def acquire(self) -> None:
        acquired: list[DeviceLock] = []
        try:
            for lock in self.locks:
                lock.acquire()
                acquired.append(lock)
        except Exception:
            for lock in reversed(acquired):
                lock.release()
            raise

    def release(self) -> None:
        for lock in reversed(self.locks):
            lock.release()
