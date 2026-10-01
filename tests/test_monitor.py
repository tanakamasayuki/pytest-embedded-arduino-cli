from pathlib import Path
import sys
import time

import pytest
import serial

import pytest_embedded_arduino_cli.plugin as plugin_module
from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.monitor import (
    MonitorTarget,
    has_own_monitor,
    is_monitor_url,
    own_monitor_protocols,
    port_protocol,
    register_protocol_handler,
)
from pytest_embedded_arduino_cli.plugin import _runtime_port_for_app
from pytest_embedded_arduino_cli.serial import is_stream_url


FAKE_CLI = """#!{python}
import os
import sys

args = sys.argv[1:]
log = os.environ.get("FAKE_MONITOR_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(repr((args, os.getcwd())) + "\\n")
out = sys.stdout.buffer
mode = os.environ.get("FAKE_MONITOR_MODE", "echo")
if mode == "fail":
    sys.stderr.write("Port monitor error: command 'open' failed: probe busy\\n")
    sys.exit(1)
if mode == "die":
    out.write(b"tick\\n")
    out.flush()
    sys.exit(0)
out.write(b"ready\\n")
out.flush()
while True:
    data = os.read(0, 4096)
    if not data:
        break
    out.write(b"echo:" + data)
    out.flush()
"""


@pytest.fixture
def fake_cli(tmp_path: Path) -> Path:
    path = tmp_path / "arduino-cli"
    path.write_text(FAKE_CLI.format(python=sys.executable), encoding="utf-8")
    path.chmod(0o755)
    return path


def _open(fake_cli: Path, sketch_dir: Path, profile: str | None = "ch32") -> serial.SerialBase:
    register_protocol_handler()
    url = MonitorTarget(
        address="/dev/ttyACM0",
        sketch_dir=sketch_dir,
        profile=profile,
        cli_path=str(fake_cli),
    ).to_url()
    return serial.serial_for_url(url, baudrate=115200, timeout=0.05)


def _read_until(port: serial.SerialBase, marker: bytes, timeout: float = 5.0) -> bytes:
    data = b""
    deadline = time.monotonic() + timeout
    while marker not in data and time.monotonic() < deadline:
        data += port.read(4096)
    return data


def test_has_own_monitor_counts_pattern_and_non_builtin_tools() -> None:
    assert has_own_monitor({"pluggable_monitor.pattern.serial": "{runtime.tools.ch32rv.path}/ch32rv monitor"})
    assert has_own_monitor({"pluggable_monitor.required.serial": "vendor:monitor-tool"})
    assert not has_own_monitor({"pluggable_monitor.required.serial": "builtin:serial-monitor"})
    assert not has_own_monitor({})
    assert not has_own_monitor({"pluggable_monitor.pattern.wlink": "x"})


def test_own_monitor_protocols_lists_every_protocol_with_a_platform_monitor() -> None:
    assert own_monitor_protocols(
        {
            "pluggable_monitor.pattern.serial": "ch32rv monitor",
            "pluggable_monitor.pattern.wchlink": "ch32rv monitor",
            "pluggable_monitor.required.oep": "ch32-riscv-ug:oep-monitor",
            "pluggable_monitor.required.network": "builtin:network-monitor",
            "upload.tool.serial": "ch32rv",
        }
    ) == {"serial", "wchlink", "oep"}


@pytest.mark.parametrize(
    ("address", "profile"),
    [
        ("/dev/ttyACM0", "ch32"),
        ("COM3", None),
        ("/dev/serial/by-id/usb-WCH_Link?x&y", "a-b"),
        ("wchlink://FBC18F0680B0", "ch32v203"),
        ("oep://30eda0e31108-hs/x035", "x035"),
    ],
)
def test_monitor_url_round_trip(tmp_path: Path, address: str, profile: str | None) -> None:
    protocol = port_protocol(address)
    target = MonitorTarget(
        address=address,
        sketch_dir=tmp_path / "my sketch",
        profile=profile,
        cli_path="/opt/a c/arduino-cli",
        protocol=protocol,
    )
    url = target.to_url()

    assert is_monitor_url(url)
    assert is_stream_url(url)
    assert MonitorTarget.from_url(url) == target


def test_monitor_command_keeps_stdin_session_and_skips_discovery(tmp_path: Path) -> None:
    target = MonitorTarget(address="/dev/ttyACM0", sketch_dir=tmp_path, profile="ch32")

    assert target.command() == [
        "arduino-cli", "monitor", "-p", "/dev/ttyACM0", "-l", "serial", "--quiet", "-m", "ch32",
    ]
    assert "-m" not in MonitorTarget(address="/dev/ttyACM0", sketch_dir=tmp_path).command()
    assert MonitorTarget(
        address="wchlink://FBC18F0680B0", sketch_dir=tmp_path, profile="ch32v203", protocol="wchlink"
    ).command() == [
        "arduino-cli", "monitor", "-p", "wchlink://FBC18F0680B0", "-l", "wchlink", "--quiet", "-m", "ch32v203",
    ]


def test_port_protocol_reads_the_scheme() -> None:
    assert port_protocol("/dev/ttyACM0") == "serial"
    assert port_protocol("COM3") == "serial"
    assert port_protocol("WCHLINK://FBC18F0680B0") == "wchlink"
    assert port_protocol("oep://30eda0e31108-hs/x035") == "oep"


def test_monitor_serial_round_trips_bytes_and_runs_in_sketch_dir(
    fake_cli: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.txt"
    monkeypatch.setenv("FAKE_MONITOR_LOG", str(log))
    sketch_dir = tmp_path / "sketch"
    sketch_dir.mkdir()
    port = _open(fake_cli, sketch_dir)
    try:
        assert _read_until(port, b"ready\n").endswith(b"ready\n")
        payload = bytes(range(256)) + b"\r\n\x00END"
        port.write(payload)
        assert _read_until(port, b"\x00END") == b"echo:" + payload
    finally:
        port.close()

    args, cwd = eval(log.read_text(encoding="utf-8").strip())
    assert args == ["monitor", "-p", "/dev/ttyACM0", "-l", "serial", "--quiet", "-m", "ch32"]
    assert Path(cwd) == sketch_dir


def test_monitor_serial_close_ends_the_child(fake_cli: Path, tmp_path: Path) -> None:
    port = _open(fake_cli, tmp_path)
    process = port._process
    _read_until(port, b"ready\n")

    port.close()

    assert process.poll() is not None
    assert not port.is_open


def test_monitor_serial_reports_open_failure_with_stderr(
    fake_cli: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MONITOR_MODE", "fail")
    port = _open(fake_cli, tmp_path)
    try:
        with pytest.raises(serial.SerialException, match=r"exit code 1\): Port monitor error: .*probe busy"):
            _read_until(port, b"never")
    finally:
        port.close()


def test_monitor_serial_reports_unexpected_end_without_reconnecting(
    fake_cli: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.txt"
    monkeypatch.setenv("FAKE_MONITOR_LOG", str(log))
    monkeypatch.setenv("FAKE_MONITOR_MODE", "die")
    port = _open(fake_cli, tmp_path)
    try:
        assert _read_until(port, b"tick\n") == b"tick\n"
        with pytest.raises(serial.SerialException, match=r"ended unexpectedly \(exit code 0\)$"):
            _read_until(port, b"never")
    finally:
        port.close()

    assert len(log.read_text(encoding="utf-8").splitlines()) == 1


def _app(tmp_path: Path, name: str, fqbn: str = "ch32-riscv-ug:ch32rv:CH32V003") -> ArduinoCliBuildConfig:
    sketch_dir = tmp_path / name
    sketch_dir.mkdir()
    (sketch_dir / "sketch.yaml").write_text(
        f"profiles:\n  ch32:\n    fqbn: {fqbn}\n    platforms:\n      - platform: ch32-riscv-ug:ch32rv (1.0.0)\n",
        encoding="utf-8",
    )
    return ArduinoCliBuildConfig(
        sketch_dir=sketch_dir,
        sketch_yaml=sketch_dir / "sketch.yaml",
        build_path=sketch_dir / "build" / "ch32",
        profile="ch32",
    )


class _Config:
    pass


def test_runtime_port_is_routed_only_for_platforms_with_own_monitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str | None]] = []
    own = {"ch32-riscv-ug:ch32rv:CH32V003": True, "esp32:esp32:esp32": False}

    def fake_show_properties(cli_path, sketch_dir, profile, **_kwargs):
        calls.append((str(sketch_dir), profile))
        fqbn = (Path(sketch_dir) / "sketch.yaml").read_text(encoding="utf-8").split("fqbn: ")[1].split("\n")[0]
        if own[fqbn]:
            return {
                "pluggable_monitor.pattern.serial": "ch32rv monitor",
                "pluggable_monitor.pattern.wchlink": "ch32rv monitor",
                "pluggable_monitor.required.oep": "ch32-riscv-ug:oep-monitor",
            }
        return {"pluggable_monitor.required.serial": "builtin:serial-monitor"}

    monkeypatch.setattr(plugin_module, "run_show_properties", fake_show_properties)
    config = _Config()
    first = _app(tmp_path, "first")
    second = _app(tmp_path, "second")
    esp = _app(tmp_path, "esp", fqbn="esp32:esp32:esp32")

    routed = _runtime_port_for_app(config, first, "/dev/ttyACM0")
    assert MonitorTarget.from_url(routed) == MonitorTarget(
        address="/dev/ttyACM0", sketch_dir=first.sketch_dir, profile="ch32"
    )
    assert is_monitor_url(_runtime_port_for_app(config, second, "/dev/ttyACM1"))
    assert _runtime_port_for_app(config, esp, "/dev/ttyUSB0") == "/dev/ttyUSB0"
    assert _runtime_port_for_app(config, first, "socket://localhost:1234") == "socket://localhost:1234"
    assert _runtime_port_for_app(config, first, None) is None
    # A URL whose scheme is a protocol the platform has a monitor for is routed.
    wchlink = MonitorTarget.from_url(_runtime_port_for_app(config, first, "wchlink://FBC18F0680B0"))
    assert (wchlink.address, wchlink.protocol) == ("wchlink://FBC18F0680B0", "wchlink")
    oep = MonitorTarget.from_url(_runtime_port_for_app(config, second, "oep://30eda0e31108-hs/x035"))
    assert (oep.address, oep.protocol) == ("oep://30eda0e31108-hs/x035", "oep")
    # Other URLs stay with pyserial, as do platforms without a monitor for the scheme.
    assert _runtime_port_for_app(config, first, "rfc2217://host:2217") == "rfc2217://host:2217"
    assert _runtime_port_for_app(config, esp, "wchlink://FBC18F0680B0") == "wchlink://FBC18F0680B0"
    # Sketches that name the same board share one probe; socket:// is never probed.
    assert [Path(sketch).name for sketch, _ in calls] == ["first", "esp"]


def test_plugin_dut_reads_through_arduino_cli_monitor(pytester: pytest.Pytester, fake_cli: Path) -> None:
    test_dir = pytester.path / "ch32_app"
    test_dir.mkdir()
    (test_dir / "build" / "ch32").mkdir(parents=True)
    (test_dir / "ch32_app.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
    (test_dir / "sketch.yaml").write_text(
        "default_profile: ch32\nprofiles:\n  ch32:\n    fqbn: ch32-riscv-ug:ch32rv:CH32V003\n",
        encoding="utf-8",
    )
    pytester.makeconftest(
        f"""
import pytest_embedded_arduino_cli.plugin as plugin_module
from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.flasher import ArduinoCliUploadConfig

ArduinoCliBuildConfig.compile = lambda self, *, check=True: None
ArduinoCliUploadConfig.upload = lambda self, *, check=True: None
plugin_module.run_show_properties = lambda cli_path, sketch_dir, profile, **kwargs: {{
    "pluggable_monitor.pattern.serial": "ch32rv monitor",
    "runtime.tools.ch32rv.path": "/tools/ch32rv",
}}
_original = ArduinoCliBuildConfig.from_test_path.__func__
ArduinoCliBuildConfig.from_test_path = classmethod(
    lambda cls, *args, **kwargs: _original(cls, *args, **{{**kwargs, "cli_path": {str(fake_cli)!r}}})
)
"""
    )
    (test_dir / "test_sample.py").write_text(
        """
def test_monitor(dut, arduino_cli_build_properties):
    assert dut.serial.port.startswith("arduinomonitor://")
    assert arduino_cli_build_properties["runtime.tools.ch32rv.path"] == "/tools/ch32rv"
    dut.expect_exact("ready")
    dut.write("ping")
    dut.expect_exact("echo:ping")
""",
        encoding="utf-8",
    )

    result = pytester.runpytest(
        str(test_dir / "test_sample.py"),
        "--run-mode=test",
        "--port=/dev/ttyACM0",
        "-p",
        "no:embedded-arduino-cli",
        "-p",
        "pytest_embedded_arduino_cli.plugin",
    )
    result.assert_outcomes(passed=1)
