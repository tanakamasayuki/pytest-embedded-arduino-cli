from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Mapping
from urllib.parse import parse_qs, quote, unquote, urlencode

from serial import PortNotOpenError, SerialBase, SerialException


#: pyserial URL scheme for a runtime port read through ``arduino-cli monitor``.
#: pyserial imports ``protocol_<scheme>`` as a module, so the scheme cannot
#: contain ``-``.
MONITOR_URL_SCHEME = "arduinomonitor"

#: Protocol of a runtime port written as a plain path, such as ``/dev/ttyACM0``.
MONITOR_PROTOCOL = "serial"

#: Seconds to wait for arduino-cli to exit after its stdin is closed.
#: Closing stdin makes arduino-cli send CLOSE to the monitor tool and exit.
MONITOR_CLOSE_TIMEOUT = 3.0


def has_own_monitor(properties: Mapping[str, str], protocol: str = MONITOR_PROTOCOL) -> bool:
    """True when the platform brings its own pluggable monitor for ``protocol``.

    ``pluggable_monitor.required.<protocol>=builtin:serial-monitor`` is the
    default arduino-cli fills in for platforms without one, so that form is
    not counted.
    """
    if properties.get(f"pluggable_monitor.pattern.{protocol}"):
        return True
    required = properties.get(f"pluggable_monitor.required.{protocol}", "")
    return bool(required) and not required.startswith("builtin:")


def own_monitor_protocols(properties: Mapping[str, str]) -> frozenset[str]:
    """Every port protocol the platform brings its own pluggable monitor for."""
    protocols = set()
    for key in properties:
        for prefix in ("pluggable_monitor.pattern.", "pluggable_monitor.required."):
            if key.startswith(prefix):
                protocols.add(key[len(prefix):])
    return frozenset(protocol for protocol in protocols if has_own_monitor(properties, protocol))


def port_protocol(port: str) -> str:
    """The arduino-cli port protocol a runtime port is written in.

    A plain path is ``serial``; ``wchlink://...`` is ``wchlink``. Whether a
    scheme names an arduino-cli protocol or a pyserial URL is decided by the
    platform's monitor, see :func:`has_own_monitor`.
    """
    if "://" not in port:
        return MONITOR_PROTOCOL
    return port.split("://", 1)[0].lower()


def is_monitor_url(port: str | None) -> bool:
    return bool(port and port.lower().startswith(f"{MONITOR_URL_SCHEME}://"))


@dataclass(frozen=True)
class MonitorTarget:
    address: str
    sketch_dir: Path
    profile: str | None = None
    cli_path: str = "arduino-cli"
    protocol: str = MONITOR_PROTOCOL

    def to_url(self) -> str:
        query = {"sketch": str(self.sketch_dir), "cli": self.cli_path, "protocol": self.protocol}
        if self.profile:
            query["profile"] = self.profile
        return f"{MONITOR_URL_SCHEME}://{quote(self.address, safe='/:')}?{urlencode(query)}"

    @classmethod
    def from_url(cls, url: str) -> "MonitorTarget":
        if not is_monitor_url(url):
            raise SerialException(f"not an {MONITOR_URL_SCHEME}:// URL: {url!r}")
        rest = url.split("://", 1)[1]
        address, _, raw_query = rest.partition("?")
        query = parse_qs(raw_query)
        sketch = query.get("sketch", [None])[0]
        if not address or not sketch:
            raise SerialException(f"{MONITOR_URL_SCHEME}:// URL needs an address and a sketch: {url!r}")
        return cls(
            address=unquote(address),
            sketch_dir=Path(sketch),
            profile=query.get("profile", [None])[0],
            cli_path=query.get("cli", ["arduino-cli"])[0],
            protocol=query.get("protocol", [MONITOR_PROTOCOL])[0],
        )

    def command(self) -> list[str]:
        command = [self.cli_path, "monitor", "-p", self.address, "-l", self.protocol, "--quiet"]
        if self.profile:
            command.extend(["-m", self.profile])
        return command


class ArduinoCliMonitorSerial(SerialBase):
    """A pyserial port backed by an ``arduino-cli monitor`` child process.

    stdout of the child is the data coming from the board, stdin is the data
    going to it. stdin stays open for the whole session: arduino-cli ends the
    session when it reaches EOF. Settings such as the baud rate are left to
    arduino-cli (board defaults, the profile's ``port_config``), so the values
    pyserial passes in are ignored.
    """

    def open(self) -> None:
        if self._port is None:
            raise SerialException("Port must be configured before it can be used.")
        if self.is_open:
            raise SerialException("Port is already open.")

        self._target = MonitorTarget.from_url(self.portstr)
        self._buffer = bytearray()
        self._condition = threading.Condition()
        self._eof = False
        self._closing = False
        self._stderr = bytearray()
        try:
            # A new session keeps Ctrl-C in the terminal from reaching
            # arduino-cli before the plugin closes it in order.
            self._process = subprocess.Popen(
                self._target.command(),
                cwd=self._target.sketch_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                start_new_session=True,
            )
        except OSError as e:
            raise SerialException(f"could not start arduino-cli monitor: {e}") from e

        self._stdout_thread = threading.Thread(target=self._pump_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._pump_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()
        self.is_open = True

    def _pump_stdout(self) -> None:
        fd = self._process.stdout.fileno()
        while True:
            try:
                data = os.read(fd, 4096)
            except OSError:
                data = b""
            with self._condition:
                if not data:
                    self._eof = True
                    self._condition.notify_all()
                    return
                self._buffer.extend(data)
                self._condition.notify_all()

    def _pump_stderr(self) -> None:
        fd = self._process.stderr.fileno()
        while True:
            try:
                data = os.read(fd, 4096)
            except OSError:
                return
            if not data:
                return
            self._stderr.extend(data)

    def _failure(self) -> SerialException:
        try:
            code = self._process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            code = None
        self._stderr_thread.join(timeout=1)
        message = f"arduino-cli monitor ended unexpectedly (exit code {code})"
        stderr = self._stderr.decode("utf-8", "replace").strip()
        if stderr:
            message = f"{message}: {stderr}"
        return SerialException(message)

    @property
    def in_waiting(self) -> int:
        if not self.is_open:
            raise PortNotOpenError
        with self._condition:
            return len(self._buffer)

    def read(self, size: int = 1) -> bytes:
        if not self.is_open:
            raise PortNotOpenError
        deadline = None if self._timeout is None else time.monotonic() + self._timeout
        with self._condition:
            while len(self._buffer) < max(size, 1) and not self._eof:
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            if not self._buffer and self._eof and not self._closing:
                raise self._failure()
            data = bytes(self._buffer[:size])
            del self._buffer[:size]
            return data

    def write(self, data: bytes) -> int:
        if not self.is_open:
            raise PortNotOpenError
        payload = memoryview(bytes(data))
        stdin = self._process.stdin
        try:
            while payload:
                written = stdin.write(payload)
                payload = payload[written:]
        except OSError as e:
            raise self._failure() from e
        return len(data)

    def close(self) -> None:
        if not self.is_open:
            return
        self._closing = True
        process = self._process
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=MONITOR_CLOSE_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=MONITOR_CLOSE_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self._stdout_thread.join(timeout=1)
        self._stderr_thread.join(timeout=1)
        stderr = self._stderr.decode("utf-8", "replace").strip()
        if stderr:
            logging.debug("arduino-cli monitor stderr: %s", stderr)
        self.is_open = False

    def reset_input_buffer(self) -> None:
        if not self.is_open:
            raise PortNotOpenError
        with self._condition:
            self._buffer.clear()

    def reset_output_buffer(self) -> None:
        if not self.is_open:
            raise PortNotOpenError

    # arduino-cli owns the port settings; pyserial's setters are accepted and ignored.
    def _reconfigure_port(self) -> None:
        pass

    def _update_rts_state(self) -> None:
        pass

    def _update_dtr_state(self) -> None:
        pass

    def _update_break_state(self) -> None:
        pass


def register_protocol_handler() -> None:
    """Let ``serial.serial_for_url`` open ``arduinomonitor://`` URLs."""
    import serial

    package = "pytest_embedded_arduino_cli.serial_handlers"
    if package not in serial.protocol_handler_packages:
        serial.protocol_handler_packages.append(package)
