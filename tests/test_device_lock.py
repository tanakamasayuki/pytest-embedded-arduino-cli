from pathlib import Path

import pytest

from pytest_embedded_arduino_cli.device_lock import (
    DeviceLock,
    DeviceLockInfo,
    DeviceLockSet,
    lock_file_name,
    normalize_device_key,
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


def test_normalize_device_key_resolves_symlink(tmp_path: Path) -> None:
    real = tmp_path / "ttyUSB0"
    real.touch()
    link = tmp_path / "by-id" / "usb-Espressif-if00"
    link.parent.mkdir()
    link.symlink_to(real)

    assert normalize_device_key(str(link)) == str(real)
    assert normalize_device_key(str(real)) == str(real)


def test_normalize_device_key_keeps_non_path_keys() -> None:
    assert normalize_device_key("COM3") == "COM3"
    assert normalize_device_key("my-custom-key") == "my-custom-key"
    assert normalize_device_key("") == ""


def test_device_lock_info_normalizes_symlinked_key(tmp_path: Path) -> None:
    real = tmp_path / "ttyUSB0"
    real.touch()
    link = tmp_path / "by-id-usb-Espressif-if00"
    link.symlink_to(real)

    info = DeviceLockInfo(key=str(link), port=str(link), role="primary")

    assert info.key == str(real)
    assert info.port == str(link)


def test_device_lock_set_rejects_symlink_alias_of_same_device(tmp_path: Path) -> None:
    real = tmp_path / "ttyUSB0"
    real.touch()
    link = tmp_path / "by-id-usb-Espressif-if00"
    link.symlink_to(real)

    infos = [
        DeviceLockInfo(key=str(real), port=str(real), role="primary"),
        DeviceLockInfo(key=str(link), port=str(link), role="peer:echo"),
    ]

    with pytest.raises(ValueError, match="duplicate device lock key"):
        DeviceLockSet(infos, lock_dir=tmp_path, timeout=0.1)


def test_lock_file_name_does_not_use_raw_path_text() -> None:
    name = lock_file_name("/dev/ttyUSB0")

    assert name.startswith("device-")
    assert name.endswith(".lock")
    assert "/" not in name
