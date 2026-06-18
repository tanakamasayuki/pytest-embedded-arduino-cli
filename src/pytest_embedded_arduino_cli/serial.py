from __future__ import annotations

import logging
import multiprocessing
from pathlib import Path
import json
import os
import queue
import threading
import time
from typing import Any
from urllib.parse import urlparse

from _pytest.config import Config


class HostArduinoPortError(RuntimeError):
    """Raised when a host Arduino socket URL cannot be completed."""


class FastSocketSerialRedirectThread(threading.Thread):
    """Batch socket:// reads so host Arduino tests do not run at one byte per tick."""

    def __init__(self, msg_queue: Any, serial_proc: Any) -> None:
        self._q = msg_queue
        self._event_q = multiprocessing.Queue()
        self._s = serial_proc
        self._block_reading = False
        threading.Thread.__init__(self, target=self._event_loop, daemon=True)

    @property
    def _is_socket(self) -> bool:
        return is_socket_url(getattr(self._s, "port", None))

    def _read_available(self) -> bytes:
        if self._is_socket:
            return self._s.read(4096)
        return self._s.read_all()

    def _event_loop(self) -> None:
        while True:
            try:
                event = self._event_q.get_nowait()
            except queue.Empty:
                event = "read"
            except OSError:
                return

            if event == "read":
                if self._block_reading:
                    time.sleep(0.05)
                    continue

                try:
                    data = self._read_available()
                except OSError as e:
                    logging.error("OSError detected: %s. Serial connection may be lost.", e)
                    return
                except Exception as e:
                    logging.warning(
                        "unknown error: %s.\nRecommend to close the serial process by `dut.serial.close()`",
                        str(e),
                    )
                    return

                try:
                    self._q.put(data)
                except OSError as e:
                    logging.warning("OSError. Error msg: %s", e)
                    return
                except Exception as e:
                    logging.warning(
                        "unknown error: %s.\nRecommend to close the serial process by `dut.serial.close()`",
                        str(e),
                    )
                    return

                if self._is_socket and not data:
                    time.sleep(0.005)

            elif event == "stop":
                self._block_reading = True
            elif event == "start":
                self._block_reading = False
            elif event == "end":
                return

            if not self._is_socket:
                time.sleep(0.05)

    def stop_reading(self) -> None:
        self._event_q.put("stop")

    def start_reading(self) -> None:
        self._event_q.put("start")

    def terminate(self) -> None:
        self._event_q.put("end")
        self.join()
        # Best-effort: after the read loop has stopped (and before the serial
        # port is closed by Serial.close), drain any bytes that arrived since
        # the last loop read and push them onto the message queue. dut.log and
        # the `-s` console are fed from the same queue, so this brings the log
        # file up to roughly `-s` completeness instead of cutting mid-line.
        # It is not a full guarantee: bytes that arrive after this final read,
        # or after the listener stops draining the queue, are still lost.
        self._drain_remaining()

    def _drain_remaining(self) -> None:
        consecutive_empty = 0
        for _ in range(50):  # hard cap so teardown cannot hang
            try:
                data = self._read_available()
            except Exception:
                return
            if data:
                try:
                    self._q.put(data)
                except Exception:
                    return
                consecutive_empty = 0
                continue
            consecutive_empty += 1
            if consecutive_empty >= 3:
                return
            time.sleep(0.01)


def normalize_profile_name(profile: str) -> str:
    return profile.upper().replace("-", "_")


def normalize_peer_name(peer: str) -> str:
    return peer.upper().replace("-", "_")


def install_fast_socket_redirect_thread() -> None:
    try:
        import pytest_embedded_serial.serial as embedded_serial
    except ImportError:
        return

    if getattr(embedded_serial, "_arduino_cli_fast_socket_redirect", False):
        return

    original_thread = embedded_serial._SerialRedirectThread

    class PatchedSerialRedirectThread(FastSocketSerialRedirectThread, original_thread):  # type: ignore[misc, valid-type]
        def __init__(self, msg_queue: Any, serial_proc: Any) -> None:
            self._arduino_cli_fast_socket = is_socket_url(getattr(serial_proc, "port", None))
            if self._arduino_cli_fast_socket:
                FastSocketSerialRedirectThread.__init__(self, msg_queue, serial_proc)
            else:
                original_thread.__init__(self, msg_queue, serial_proc)

        def _event_loop(self) -> None:
            if getattr(self, "_arduino_cli_fast_socket", False):
                FastSocketSerialRedirectThread._event_loop(self)
            else:
                original_thread._event_loop(self)

    embedded_serial._SerialRedirectThread = PatchedSerialRedirectThread
    embedded_serial._arduino_cli_fast_socket_redirect = True


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


def resolve_peer_port(
    *,
    peer: str,
    profile: str | None,
    option_port: str | None = None,
    profile_port: str | None = None,
) -> str | None:
    if option_port:
        return option_port

    normalized_peer = normalize_peer_name(peer)
    if profile:
        env_profile_port = os.getenv(
            f"TEST_SERIAL_PORT_PEER_{normalized_peer}_{normalize_profile_name(profile)}"
        )
        if env_profile_port:
            return env_profile_port

    env_port = os.getenv(f"TEST_SERIAL_PORT_PEER_{normalized_peer}")
    if env_port:
        return env_port

    if is_socket_url(profile_port):
        return profile_port

    return None


def resolve_peer_upload_port(runtime_port: str | None) -> str | None:
    if runtime_port and is_socket_url(runtime_port):
        return None
    return runtime_port


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
