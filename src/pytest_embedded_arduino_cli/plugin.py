from __future__ import annotations

from pathlib import Path
import shlex
from typing import Any

import pytest

from .app import ArduinoCliBuildConfig, SketchConfigError, resolve_sketch_dir, resolve_test_path
from .flasher import ArduinoCliUploadConfig
from .serial import ensure_default_embedded_services, resolve_port, resolve_upload_port


def _should_build(run_mode: str) -> bool:
    return run_mode in ("all", "build")


def _should_upload(run_mode: str) -> bool:
    return run_mode in ("all", "test")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("arduino-cli")
    group.addoption(
        "--run-mode",
        action="store",
        choices=("all", "build", "test"),
        default="all",
        help="Select whether to run build only, upload-and-test with existing artifacts, or build-upload-test.",
    )
    group.addoption(
        "--profile",
        action="store",
        help="Arduino CLI sketch profile name from sketch.yaml.",
    )


def pytest_report_header(config: pytest.Config) -> list[str]:
    return [
        f"arduino-cli run-mode: {config.getoption('run_mode')}",
        f"arduino-cli profile: {config.getoption('profile') or 'default'}",
    ]


def pytest_configure(config: pytest.Config) -> None:
    ensure_default_embedded_services(config)


def _request_path(request: pytest.FixtureRequest) -> Path:
    if hasattr(request, "path"):
        return Path(request.path)
    return Path(str(request.fspath))


def _request_has_sketch(request: pytest.FixtureRequest) -> bool:
    test_path = resolve_test_path(_request_path(request))
    return any(test_path.glob("*.ino"))


def _terminal_reporter(config: pytest.Config) -> Any | None:
    return config.pluginmanager.getplugin("terminalreporter")


def _verbose_level(config: pytest.Config) -> int:
    return int(getattr(config.option, "verbose", 0) or 0)


def _log_command(
    config: pytest.Config,
    *,
    action: str,
    command: list[str],
    details: dict[str, str | None],
) -> None:
    verbosity = _verbose_level(config)
    if verbosity < 1:
        return

    reporter = _terminal_reporter(config)
    if reporter is None:
        return

    reporter.write_line(f"[arduino-cli] {action}: {shlex.join(command)}")
    if verbosity < 2:
        return

    for key, value in details.items():
        if value is None:
            continue
        reporter.write_line(f"[arduino-cli] {action} {key}: {value}")


@pytest.fixture
def app_path(request: pytest.FixtureRequest) -> str:
    return str(resolve_sketch_dir(_request_path(request)))


@pytest.fixture
def build_dir(request: pytest.FixtureRequest) -> str:
    return str(_build_config_from_request(request).build_path)


@pytest.fixture
def skip_autoflash() -> bool:
    # Build/upload are handled explicitly by this plugin instead of pytest-embedded services.
    return True


def _build_config_from_request(
    request: pytest.FixtureRequest,
    *,
    required: bool = True,
) -> ArduinoCliBuildConfig | None:
    config = request.config
    should_require = required or _request_has_sketch(request)
    try:
        return ArduinoCliBuildConfig.from_test_path(
            _request_path(request),
            profile=config.getoption("profile"),
        )
    except SketchConfigError:
        if should_require:
            raise
        return None


@pytest.fixture(scope="module")
def arduino_cli_app(request: pytest.FixtureRequest) -> ArduinoCliBuildConfig:
    return _build_config_from_request(request)


@pytest.fixture(scope="module")
def arduino_cli_flasher(
    request: pytest.FixtureRequest,
    arduino_cli_app: ArduinoCliBuildConfig,
) -> ArduinoCliUploadConfig:
    return ArduinoCliUploadConfig.from_build_config(
        arduino_cli_app,
        port=resolve_upload_port(request.config, profile=arduino_cli_app.profile),
    )


@pytest.fixture(scope="module", autouse=True)
def arduino_cli_resolved_port(request: pytest.FixtureRequest) -> None:
    arduino_cli_app = _build_config_from_request(request, required=False)
    if arduino_cli_app is None:
        return

    if getattr(request.config.option, "flash_port", None):
        return
    if getattr(request.config.option, "port", None):
        return

    resolved_port = resolve_port(request.config, profile=arduino_cli_app.profile)
    if resolved_port:
        request.config.option.port = resolved_port


@pytest.fixture(scope="module", autouse=True)
def arduino_cli_build(
    request: pytest.FixtureRequest,
    arduino_cli_resolved_port: None,
) -> None:
    arduino_cli_app = _build_config_from_request(request, required=False)
    if arduino_cli_app is None:
        return
    if not _should_build(request.config.getoption("run_mode")):
        return

    _log_command(
        request.config,
        action="compile",
        command=arduino_cli_app.build_command(),
        details={
            "cwd": str(arduino_cli_app.sketch_dir),
            "sketch_dir": str(arduino_cli_app.sketch_dir),
            "build_path": str(arduino_cli_app.build_path),
            "profile": arduino_cli_app.profile,
        },
    )
    arduino_cli_app.compile()


@pytest.fixture(scope="module", autouse=True)
def arduino_cli_upload(
    request: pytest.FixtureRequest,
    arduino_cli_build: None,
    arduino_cli_resolved_port: None,
) -> None:
    run_mode = request.config.getoption("run_mode")
    if not _should_upload(run_mode):
        return
    arduino_cli_app = _build_config_from_request(request, required=False)
    if arduino_cli_app is None:
        return
    if not arduino_cli_app.build_path.is_dir():
        raise FileNotFoundError(
            f"build output directory not found: {arduino_cli_app.build_path}. "
            "Run with --run-mode=all first, or build the sketch before --run-mode=test."
        )

    arduino_cli_flasher = ArduinoCliUploadConfig.from_build_config(
        arduino_cli_app,
        port=resolve_upload_port(request.config, profile=arduino_cli_app.profile),
    )

    _log_command(
        request.config,
        action="upload",
        command=arduino_cli_flasher.upload_command(),
        details={
            "cwd": str(arduino_cli_flasher.sketch_dir),
            "sketch_dir": str(arduino_cli_flasher.sketch_dir),
            "build_path": str(arduino_cli_flasher.build_path),
            "profile": arduino_cli_flasher.profile,
            "port": arduino_cli_flasher.port,
        },
    )
    arduino_cli_flasher.upload()


@pytest.fixture(autouse=True)
def skip_test_execution_in_build_mode(
    request: pytest.FixtureRequest,
    arduino_cli_build: None,
) -> None:
    if request.config.getoption("run_mode") == "build":
        pytest.skip("skipped test execution in build-only mode")
