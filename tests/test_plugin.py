from pathlib import Path

import pytest

from pytest_embedded_arduino_cli.plugin import _log_command, _should_build, _should_upload
from pytest_embedded_arduino_cli.serial import (
    ensure_default_embedded_services,
    normalize_profile_name,
    resolve_port,
    resolve_upload_port,
)


class DummyReporter:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write_line(self, message: str) -> None:
        self.lines.append(message)


class DummyPluginManager:
    def __init__(self, reporter: DummyReporter | None) -> None:
        self.reporter = reporter

    def getplugin(self, name: str) -> DummyReporter | None:
        assert name == "terminalreporter"
        return self.reporter


class DummyConfig:
    def __init__(self, verbose: int, reporter: DummyReporter | None, embedded_services: str | None = None) -> None:
        self.option = type(
            "Option",
            (),
            {
                "verbose": verbose,
                "embedded_services": embedded_services,
            },
        )()
        self.pluginmanager = DummyPluginManager(reporter)


def test_plugin_help_lists_options(pytester: pytest.Pytester) -> None:
    result = pytester.runpytest(
        "--help",
        "-p",
        "no:embedded-arduino-cli",
        "-p",
        "pytest_embedded_arduino_cli.plugin",
    )
    stdout = result.stdout.str()
    assert "--run-mode={all,build,test}" in stdout
    assert "--profile=PROFILE" in stdout
    assert "--arduino-cli-build-path" not in stdout
    assert "--arduino-cli-upload-port" not in stdout


def test_plugin_fixtures_resolve_app_and_build_dir(pytester: pytest.Pytester) -> None:
    test_dir = pytester.path / "sample_app"
    test_dir.mkdir()
    (test_dir / "build" / "uno").mkdir(parents=True)
    (test_dir / "sample_app.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
    (test_dir / "sketch.yaml").write_text(
        "default_profile: uno\nprofiles:\n  uno: {}\n",
        encoding="utf-8",
    )
    pytester.makeconftest(
        """
from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.flasher import ArduinoCliUploadConfig


def _fake_compile(self, *, check=True):
    return None


def _fake_upload(self, *, check=True):
    return None


ArduinoCliBuildConfig.compile = _fake_compile
ArduinoCliUploadConfig.upload = _fake_upload
"""
    )
    (test_dir / "test_sample.py").write_text(
        """
def test_paths(arduino_cli_app):
    assert str(arduino_cli_app.sketch_dir).endswith("sample_app")
    assert str(arduino_cli_app.build_path).endswith("sample_app/build/uno")
""",
        encoding="utf-8",
    )

    result = pytester.runpytest(
        str(test_dir / "test_sample.py"),
        "--run-mode=test",
        "-p",
        "no:embedded-arduino-cli",
        "-p",
        "pytest_embedded_arduino_cli.plugin",
    )
    result.assert_outcomes(passed=1)


def test_log_command_respects_v_level() -> None:
    reporter = DummyReporter()
    config = DummyConfig(verbose=1, reporter=reporter)

    _log_command(
        config,
        action="compile",
        command=["arduino-cli", "compile", "/tmp/app"],
        details={"cwd": "/tmp/app", "profile": "uno"},
    )

    assert reporter.lines == ["[arduino-cli] compile: arduino-cli compile /tmp/app"]


def test_log_command_respects_vv_level() -> None:
    reporter = DummyReporter()
    config = DummyConfig(verbose=2, reporter=reporter)

    _log_command(
        config,
        action="upload",
        command=["arduino-cli", "upload", "--port", "/dev/ttyACM0", "/tmp/app"],
        details={"cwd": "/tmp/app", "build_path": "/tmp/app/build/uno", "port": "/dev/ttyACM0"},
    )

    assert reporter.lines == [
        "[arduino-cli] upload: arduino-cli upload --port /dev/ttyACM0 /tmp/app",
        "[arduino-cli] upload cwd: /tmp/app",
        "[arduino-cli] upload build_path: /tmp/app/build/uno",
        "[arduino-cli] upload port: /dev/ttyACM0",
    ]


def test_run_mode_build_matrix() -> None:
    assert _should_build("all") is True
    assert _should_build("build") is True
    assert _should_build("test") is False


def test_run_mode_upload_matrix() -> None:
    assert _should_upload("all") is True
    assert _should_upload("build") is False
    assert _should_upload("test") is True


def test_default_embedded_services_is_serial() -> None:
    config = DummyConfig(verbose=0, reporter=None, embedded_services=None)

    ensure_default_embedded_services(config)

    assert config.option.embedded_services == "serial"


def test_default_embedded_services_appends_serial() -> None:
    config = DummyConfig(verbose=0, reporter=None, embedded_services="idf")

    ensure_default_embedded_services(config)

    assert config.option.embedded_services == "idf,serial"


def test_normalize_profile_name() -> None:
    assert normalize_profile_name("esp32-s3") == "ESP32_S3"


def test_resolve_upload_port_prefers_profile_env(monkeypatch: pytest.MonkeyPatch) -> None:
    config = DummyConfig(verbose=0, reporter=None)
    config.option.port = None
    config.option.flash_port = None
    config.option.profile = "esp32-s3"
    monkeypatch.setenv("TEST_SERIAL_PORT_ESP32_S3", "/dev/ttyUSB1")

    assert resolve_upload_port(config) == "/dev/ttyUSB1"


def test_resolve_upload_port_falls_back_to_common_env(monkeypatch: pytest.MonkeyPatch) -> None:
    config = DummyConfig(verbose=0, reporter=None)
    config.option.port = None
    config.option.flash_port = None
    config.option.profile = None
    monkeypatch.setenv("TEST_SERIAL_PORT", "/dev/ttyUSB0")

    assert resolve_upload_port(config) == "/dev/ttyUSB0"


def test_resolve_port_uses_explicit_profile_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    config = DummyConfig(verbose=0, reporter=None)
    config.option.port = None
    config.option.flash_port = None
    config.option.profile = None
    monkeypatch.setenv("TEST_SERIAL_PORT_ESP32", "/dev/ttyUSB0")

    assert resolve_port(config, profile="esp32") == "/dev/ttyUSB0"
