from pathlib import Path

import pytest

from pytest_embedded_arduino_cli.device_lock import (
    DeviceLock,
    DeviceLockInfo,
    DeviceLockSet,
    lock_file_name,
    read_lock_metadata,
)


def test_device_lock_writes_metadata_and_releases_os_lock(tmp_path: Path) -> None:
    info = DeviceLockInfo(
        key="/dev/ttyUSB0",
        port="/dev/ttyUSB0",
        profile="esp32",
        sketch_dir="/tmp/sketch",
        role="primary",
    )
    lock = DeviceLock(info, lock_dir=tmp_path, timeout=0.1)

    lock.acquire()
    path = tmp_path / lock_file_name("/dev/ttyUSB0")
    metadata = read_lock_metadata(path)
    assert metadata is not None
    assert metadata["key"] == "/dev/ttyUSB0"
    assert metadata["port"] == "/dev/ttyUSB0"
    assert metadata["profile"] == "esp32"
    lock.release()

    second = DeviceLock(info, lock_dir=tmp_path, timeout=0.1)
    second.acquire()
    second.release()


def test_device_lock_set_rejects_duplicate_keys(tmp_path: Path) -> None:
    infos = [
        DeviceLockInfo(key="/dev/ttyUSB0", port="/dev/ttyUSB0", role="primary"),
        DeviceLockInfo(key="/dev/ttyUSB0", port="/dev/ttyUSB0", role="peer:echo"),
    ]

    with pytest.raises(ValueError, match="duplicate device lock key"):
        DeviceLockSet(infos, lock_dir=tmp_path, timeout=0.1)


def test_lock_file_name_does_not_use_raw_path_text() -> None:
    name = lock_file_name("/dev/ttyUSB0")

    assert name.startswith("device-")
    assert name.endswith(".lock")
    assert "/" not in name
