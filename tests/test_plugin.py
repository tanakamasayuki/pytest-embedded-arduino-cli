from pathlib import Path
import sys
import types

import pytest

from pytest_embedded_arduino_cli.plugin import (
    _ardutest_artifact_dir,
    _log_command,
    _set_optional_metadata,
    _should_build,
    _should_upload,
)
from pytest_embedded_arduino_cli.serial import (
    complete_host_arduino_socket_url,
    ensure_default_embedded_services,
    find_host_arduino_port,
    is_socket_url,
    normalize_profile_name,
    read_host_arduino_port,
    resolve_port,
    resolve_upload_port,
    socket_url_needs_port_completion,
    wait_for_socket_url,
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
                "profile": None,
                "arduino_test_artifact_dir": "ardutest",
                "clean": False,
            },
        )()
        self.pluginmanager = DummyPluginManager(reporter)
        self.stash = {}
        self.rootpath = Path.cwd()

    def getoption(self, name: str):
        return getattr(self.option, name)


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
    assert "--arduino-test-timeout=ARDUINO_TEST_TIMEOUT" in stdout
    assert "--arduino-test-artifact-dir=ARDUINO_TEST_ARTIFACT_DIR" in stdout
    assert "--clean" in stdout
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


def test_plugin_passes_clean_to_build_config(pytester: pytest.Pytester) -> None:
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
    assert self.clean is True
    assert "--clean" in self.build_command()
    return None


def _fake_upload(self, *, check=True):
    return None


ArduinoCliBuildConfig.compile = _fake_compile
ArduinoCliUploadConfig.upload = _fake_upload
"""
    )
    (test_dir / "test_sample.py").write_text(
        """
def test_clean_option(arduino_cli_app):
    assert arduino_cli_app.clean is True
""",
        encoding="utf-8",
    )

    result = pytester.runpytest(
        str(test_dir / "test_sample.py"),
        "--clean",
        "-p",
        "no:embedded-arduino-cli",
        "-p",
        "pytest_embedded_arduino_cli.plugin",
    )
    result.assert_outcomes(passed=1)


def test_clean_option_removes_ardutest_artifact_dir(pytester: pytest.Pytester) -> None:
    artifact_dir = pytester.path / "ardutest"
    artifact_dir.mkdir()
    (artifact_dir / "old.txt").write_text("old", encoding="utf-8")
    pytester.makepyfile(
        """
def test_artifact_dir_removed():
    from pathlib import Path

    assert not Path("ardutest").exists()
"""
    )

    result = pytester.runpytest(
        "--clean",
        "-p",
        "no:embedded-arduino-cli",
        "-p",
        "pytest_embedded_arduino_cli.plugin",
    )

    result.assert_outcomes(passed=1)
    assert not artifact_dir.exists()


def test_ardutest_artifact_dir_resolves_relative_to_pytest_root(tmp_path: Path) -> None:
    config = DummyConfig(verbose=0, reporter=None)
    config.rootpath = tmp_path

    assert _ardutest_artifact_dir(config) == tmp_path / "ardutest"


def test_plugin_completes_host_arduino_socket_port(pytester: pytest.Pytester) -> None:
    test_dir = pytester.path / "host_app"
    test_dir.mkdir()
    build_dir = test_dir / "build" / "host"
    build_dir.mkdir(parents=True)
    (test_dir / "host_app.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
    (test_dir / "sketch.yaml").write_text(
        "default_profile: host\nprofiles:\n  host: {}\n",
        encoding="utf-8",
    )
    pytester.makeconftest(
        """
from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.flasher import ArduinoCliUploadConfig


def _fake_compile(self, *, check=True):
    self.build_path.mkdir(parents=True, exist_ok=True)
    return None


def _fake_upload(self, *, check=True):
    assert self.port is None
    (self.build_path / "host_app.ino.out.host-arduino.json").write_text(
        '{"pid": 21228, "port": 56789}',
        encoding="utf-8",
    )
    return None


ArduinoCliBuildConfig.compile = _fake_compile
ArduinoCliUploadConfig.upload = _fake_upload
"""
    )
    (test_dir / "test_sample.py").write_text(
        """
def test_port_was_completed(request):
    assert request.config.option.port == "socket://localhost:56789"
""",
        encoding="utf-8",
    )

    result = pytester.runpytest(
        str(test_dir / "test_sample.py"),
        "--run-mode=test",
        "--port=socket://localhost",
        "-p",
        "no:embedded-arduino-cli",
        "-p",
        "pytest_embedded_arduino_cli.plugin",
    )
    result.assert_outcomes(passed=1)


def test_wait_for_socket_url_ignores_incomplete_socket_url() -> None:
    wait_for_socket_url("socket://localhost", timeout=0.01)


def test_plugin_uses_socket_profile_port_from_sketch_yaml(pytester: pytest.Pytester) -> None:
    test_dir = pytester.path / "host_app"
    test_dir.mkdir()
    build_dir = test_dir / "build" / "host"
    build_dir.mkdir(parents=True)
    (test_dir / "host_app.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
    (test_dir / "sketch.yaml").write_text(
        "default_profile: host\nprofiles:\n  host:\n    port: socket://localhost\n",
        encoding="utf-8",
    )
    pytester.makeconftest(
        """
from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.flasher import ArduinoCliUploadConfig


def _fake_compile(self, *, check=True):
    self.build_path.mkdir(parents=True, exist_ok=True)
    return None


def _fake_upload(self, *, check=True):
    assert self.port is None
    (self.build_path / "host_app.ino.out.host-arduino.json").write_text(
        '{"pid": 21228, "port": 56789}',
        encoding="utf-8",
    )
    return None


ArduinoCliBuildConfig.compile = _fake_compile
ArduinoCliUploadConfig.upload = _fake_upload
"""
    )
    (test_dir / "test_sample.py").write_text(
        """
def test_port_was_completed_from_sketch_yaml(request):
    assert request.config.option.port == "socket://localhost:56789"
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


def test_plugin_ignores_non_socket_profile_port(pytester: pytest.Pytester) -> None:
    test_dir = pytester.path / "host_app"
    test_dir.mkdir()
    build_dir = test_dir / "build" / "host"
    build_dir.mkdir(parents=True)
    (test_dir / "host_app.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
    (test_dir / "sketch.yaml").write_text(
        "default_profile: host\nprofiles:\n  host:\n    port: /dev/ttyUSB0\n",
        encoding="utf-8",
    )
    pytester.makeconftest(
        """
from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.flasher import ArduinoCliUploadConfig


def _fake_compile(self, *, check=True):
    self.build_path.mkdir(parents=True, exist_ok=True)
    return None


def _fake_upload(self, *, check=True):
    assert self.port is None
    return None


ArduinoCliBuildConfig.compile = _fake_compile
ArduinoCliUploadConfig.upload = _fake_upload
"""
    )
    (test_dir / "test_sample.py").write_text(
        """
def test_port_was_not_read_from_sketch_yaml(request):
    assert request.config.option.port is None
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


def test_plugin_prefers_env_port_over_sketch_yaml(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_dir = pytester.path / "host_app"
    test_dir.mkdir()
    build_dir = test_dir / "build" / "host"
    build_dir.mkdir(parents=True)
    (test_dir / "host_app.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
    (test_dir / "sketch.yaml").write_text(
        "default_profile: host\nprofiles:\n  host:\n    port: socket://localhost\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_SERIAL_PORT_HOST", "socket://127.0.0.1")
    pytester.makeconftest(
        """
from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.flasher import ArduinoCliUploadConfig


def _fake_compile(self, *, check=True):
    self.build_path.mkdir(parents=True, exist_ok=True)
    return None


def _fake_upload(self, *, check=True):
    assert self.port is None
    (self.build_path / "host_app.ino.out.host-arduino.json").write_text(
        '{"pid": 21228, "port": 56789}',
        encoding="utf-8",
    )
    return None


ArduinoCliBuildConfig.compile = _fake_compile
ArduinoCliUploadConfig.upload = _fake_upload
"""
    )
    (test_dir / "test_sample.py").write_text(
        """
def test_env_port_was_completed(request):
    assert request.config.option.port == "socket://127.0.0.1:56789"
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


def test_plugin_resets_completed_socket_port_for_each_sketch(pytester: pytest.Pytester) -> None:
    root = pytester.path / "examples"
    app09 = root / "09_host_arduino_core" / "host_smoke"
    app10 = root / "10_build_flags" / "build_flag_switch"
    app09.mkdir(parents=True)
    app10.mkdir(parents=True)

    for sketch_dir in (app09, app10):
        (sketch_dir / f"{sketch_dir.name}.ino").write_text(
            "void setup() {}\nvoid loop() {}\n",
            encoding="utf-8",
        )
        (sketch_dir / "sketch.yaml").write_text(
            "default_profile: host\nprofiles:\n  host:\n    port: socket://localhost\n",
            encoding="utf-8",
        )

    pytester.makeconftest(
        """
from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.flasher import ArduinoCliUploadConfig


def _fake_compile(self, *, check=True):
    self.build_path.mkdir(parents=True, exist_ok=True)
    return None


def _fake_upload(self, *, check=True):
    assert self.port is None
    runtime_port = 11111 if self.sketch_dir.name == "host_smoke" else 22222
    (self.build_path / f"{self.sketch_dir.name}.ino.out.host-arduino.json").write_text(
        f'{{"pid": 21228, "port": {runtime_port}}}',
        encoding="utf-8",
    )
    return None


ArduinoCliBuildConfig.compile = _fake_compile
ArduinoCliUploadConfig.upload = _fake_upload
"""
    )
    (app09 / "test_host_smoke.py").write_text(
        """
def test_first_sketch_port(request):
    assert request.config.option.port == "socket://localhost:11111"
""",
        encoding="utf-8",
    )
    (app10 / "test_build_flag_switch.py").write_text(
        """
def test_second_sketch_port(request):
    assert request.config.option.port == "socket://localhost:22222"
""",
        encoding="utf-8",
    )

    result = pytester.runpytest(
        str(root),
        "--profile=host",
        "-p",
        "no:embedded-arduino-cli",
        "-p",
        "pytest_embedded_arduino_cli.plugin",
    )
    result.assert_outcomes(passed=2)


def test_plugin_skips_unsupported_profile_before_build(pytester: pytest.Pytester) -> None:
    test_dir = pytester.path / "sample_app"
    test_dir.mkdir()
    (test_dir / "sample_app.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
    (test_dir / "sketch.yaml").write_text(
        "default_profile: esp32\nprofiles:\n  esp32: {}\n",
        encoding="utf-8",
    )
    (test_dir / "test_sample.py").write_text(
        """
def test_never_reached():
    assert False
""",
        encoding="utf-8",
    )

    result = pytester.runpytest(
        str(test_dir / "test_sample.py"),
        "--profile",
        "uno",
        "-p",
        "no:embedded-arduino-cli",
        "-p",
        "pytest_embedded_arduino_cli.plugin",
    )
    result.assert_outcomes(skipped=1)


def test_plugin_does_not_require_ino_for_plain_python_tests(pytester: pytest.Pytester) -> None:
    test_dir = pytester.path / "plain_tests"
    test_dir.mkdir()
    (test_dir / "test_plain.py").write_text(
        """
def test_plain():
    assert True
""",
        encoding="utf-8",
    )

    result = pytester.runpytest(
        str(test_dir / "test_plain.py"),
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


def test_resolve_upload_port_omits_socket_runtime_port() -> None:
    config = DummyConfig(verbose=0, reporter=None)
    config.option.port = "socket://localhost"
    config.option.flash_port = None

    assert resolve_upload_port(config) is None


def test_resolve_upload_port_prefers_flash_port_over_socket_runtime_port() -> None:
    config = DummyConfig(verbose=0, reporter=None)
    config.option.port = "socket://localhost"
    config.option.flash_port = "/dev/ttyACM0"

    assert resolve_upload_port(config) == "/dev/ttyACM0"


def test_resolve_port_uses_explicit_profile_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    config = DummyConfig(verbose=0, reporter=None)
    config.option.port = None
    config.option.flash_port = None
    config.option.profile = None
    monkeypatch.setenv("TEST_SERIAL_PORT_ESP32", "/dev/ttyUSB0")

    assert resolve_port(config, profile="esp32") == "/dev/ttyUSB0"


def test_socket_url_helpers() -> None:
    assert is_socket_url("socket://localhost") is True
    assert is_socket_url("/dev/ttyUSB0") is False
    assert socket_url_needs_port_completion("socket://localhost") is True
    assert socket_url_needs_port_completion("socket://localhost:56789") is False


def test_read_host_arduino_port(tmp_path: Path) -> None:
    info_path = tmp_path / "host_app.ino.out.host-arduino.json"
    info_path.write_text('{"pid": 21228, "port": 56789}', encoding="utf-8")

    assert read_host_arduino_port(info_path) == 56789


def test_find_host_arduino_port(tmp_path: Path) -> None:
    build_path = tmp_path / "build" / "host"
    build_path.mkdir(parents=True)
    (build_path / "host_app.ino.out.host-arduino.json").write_text(
        '{"pid": 21228, "port": 56789}',
        encoding="utf-8",
    )

    assert find_host_arduino_port(build_path) == 56789


def test_complete_host_arduino_socket_url(tmp_path: Path) -> None:
    build_path = tmp_path / "build" / "host"
    build_path.mkdir(parents=True)
    (build_path / "host_app.ino.out.host-arduino.json").write_text(
        '{"pid": 21228, "port": 56789}',
        encoding="utf-8",
    )

    assert (
        complete_host_arduino_socket_url("socket://127.0.0.1", build_path)
        == "socket://127.0.0.1:56789"
    )


def test_set_optional_metadata_adds_profile_when_pytest_metadata_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_key = object()
    plugin_module = types.ModuleType("pytest_metadata.plugin")
    plugin_module.metadata_key = metadata_key
    pytest_metadata_pkg = types.ModuleType("pytest_metadata")

    monkeypatch.setitem(sys.modules, "pytest_metadata", pytest_metadata_pkg)
    monkeypatch.setitem(sys.modules, "pytest_metadata.plugin", plugin_module)

    config = DummyConfig(verbose=0, reporter=None)
    config.option.profile = "esp32"
    config.stash[metadata_key] = {}

    _set_optional_metadata(config)

    assert config.stash[metadata_key]["Profile"] == "esp32"


def test_set_optional_metadata_ignores_missing_pytest_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "pytest_metadata.plugin", raising=False)
    monkeypatch.delitem(sys.modules, "pytest_metadata", raising=False)

    config = DummyConfig(verbose=0, reporter=None)

    _set_optional_metadata(config)
