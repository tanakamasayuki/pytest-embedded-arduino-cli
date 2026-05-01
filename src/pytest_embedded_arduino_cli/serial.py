from __future__ import annotations

from pathlib import Path
import json
import os
import time
from urllib.parse import urlparse

from _pytest.config import Config


class HostArduinoPortError(RuntimeError):
    """Raised when a host Arduino socket URL cannot be completed."""


def normalize_profile_name(profile: str) -> str:
    return profile.upper().replace("-", "_")


def ensure_default_embedded_services(config: Config) -> None:
    current = getattr(config.option, "embedded_services", None)
    if not current:
        config.option.embedded_services = "serial"
        return

    services = [service.strip() for service in current.split(",") if service.strip()]
    if "serial" in services:
        return

    services.append("serial")
    config.option.embedded_services = ",".join(services)


def resolve_port(config: Config, profile: str | None = None) -> str | None:
    flash_port = getattr(config.option, "flash_port", None)
    if flash_port:
        return flash_port

    port = getattr(config.option, "port", None)
    if port:
        return port

    if profile is None:
        profile = getattr(config.option, "profile", None)

    if profile:
        profile_port = os.getenv(f"TEST_SERIAL_PORT_{normalize_profile_name(profile)}")
        if profile_port:
            return profile_port

    return os.getenv("TEST_SERIAL_PORT")


def resolve_upload_port(config: Config, profile: str | None = None) -> str | None:
    flash_port = getattr(config.option, "flash_port", None)
    if flash_port:
        return flash_port

    port = getattr(config.option, "port", None)
    if port:
        if is_socket_url(port):
            return None
        return port

    if profile is None:
        profile = getattr(config.option, "profile", None)

    if profile:
        profile_port = os.getenv(f"TEST_SERIAL_PORT_{normalize_profile_name(profile)}")
        if profile_port:
            return None if is_socket_url(profile_port) else profile_port

    env_port = os.getenv("TEST_SERIAL_PORT")
    if env_port and is_socket_url(env_port):
        return None
    return env_port


def is_socket_url(port: str | None) -> bool:
    return bool(port and port.startswith("socket://"))


def socket_url_has_port(port: str | None) -> bool:
    if not is_socket_url(port):
        return False

    try:
        return urlparse(port).port is not None
    except ValueError:
        return False


def socket_url_needs_port_completion(port: str | None) -> bool:
    return is_socket_url(port) and not socket_url_has_port(port)


def complete_socket_url(port: str, runtime_port: int) -> str:
    parsed = urlparse(port)
    host = parsed.netloc or parsed.hostname or "localhost"
    return f"socket://{host}:{runtime_port}"


def read_host_arduino_port(path: str | Path) -> int | None:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    port = data.get("port")
    if not isinstance(port, int):
        return None
    if not 1 <= port <= 65535:
        return None

    return port


def find_host_arduino_port(build_path: str | Path) -> int | None:
    root = Path(build_path)
    if not root.is_dir():
        return None

    candidates = sorted(
        root.rglob("*.host-arduino.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        port = read_host_arduino_port(candidate)
        if port is not None:
            return port

    return None


def complete_host_arduino_socket_url(port: str, build_path: str | Path) -> str:
    runtime_port = find_host_arduino_port(build_path)
    if runtime_port is None:
        raise HostArduinoPortError(
            "host Arduino port file not found under build output directory: "
            f"{Path(build_path)}"
        )

    return complete_socket_url(port, runtime_port)


def wait_for_socket_url(port: str, timeout: float = 0.3, interval: float = 0.05) -> None:
    if not socket_url_has_port(port):
        return

    # host-arduino writes the runtime port file before pytest-embedded opens
    # the serial socket. A short passive delay avoids racing the listener
    # without consuming the single socket connection with a readiness probe.
    del interval
    time.sleep(max(timeout, 0.0))
