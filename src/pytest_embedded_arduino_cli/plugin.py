from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import shlex
from typing import Any, Callable

import pytest

from .ardutest import ArduTestSession
from .app import (
    ArduinoCliBuildConfig,
    SketchConfigError,
    UnsupportedProfileError,
    detect_build_property,
    resolve_sketch_dir,
    resolve_test_path,
    run_show_properties,
)
from .flasher import ArduinoCliUploadConfig
from .serial import (
    complete_host_arduino_socket_url,
    ensure_default_embedded_services,
    install_fast_socket_redirect_thread,
    is_socket_url,
    resolve_peer_port,
    resolve_peer_upload_port,
    resolve_port,
    resolve_upload_port,
    socket_url_needs_port_completion,
    wait_for_socket_url,
)
from .state_cache import StateCache


@dataclass(frozen=True)
class PeerTarget:
    name: str
    app: ArduinoCliBuildConfig
    runtime_port: str | None


class PeerDutMap(dict[str, Any]):
    pass


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
    group.addoption(
        "--peer-profile",
        action="append",
        default=[],
        metavar="NAME:PROFILE",
        help="Set a peer DUT profile. May be specified multiple times.",
    )
    group.addoption(
        "--peer-port",
        action="append",
        default=[],
        metavar="NAME:PORT",
        help="Set a peer DUT runtime port. May be specified multiple times.",
    )
    group.addoption(
        "--arduino-test-timeout",
        action="store",
        type=float,
        default=30.0,
        help="Timeout in seconds while waiting for ArduTest serial output.",
    )
    group.addoption(
        "--arduino-test-artifact-dir",
        action="store",
        default="ardutest",
        help="Directory for ArduTest artifacts, relative to pytest rootdir unless absolute.",
    )
    group.addoption(
        "--arduino-test-missing-config",
        action="store",
        choices=("skip", "error"),
        default="skip",
        help="Treat missing required ArduTest config as skipped tests or pytest errors.",
    )
    group.addoption(
        "--clean",
        action="store_true",
        default=False,
        help="Pass --clean to arduino-cli compile and remove ArduTest artifacts before running.",
    )
    group.addoption(
        "--save-state",
        action="store_true",
        default=False,
        help="Save test verification state to state.json for local development.",
    )
    group.addoption(
        "--save-state-dir",
        action="store",
        default=".pytest-results",
        help="Directory to save state.json (relative to pytest rootdir unless absolute).",
    )


def pytest_report_header(config: pytest.Config) -> list[str]:
    return [
        f"arduino-cli run-mode: {config.getoption('run_mode')}",
        f"arduino-cli profile: {config.getoption('profile') or 'default'}",
    ]


def pytest_configure(config: pytest.Config) -> None:
    install_fast_socket_redirect_thread()
    _remember_initial_ports(config)
    _clean_ardutest_artifacts(config)
    ensure_default_embedded_services(config)
    _set_optional_metadata(config)
    _initialize_state_cache(config)


def _remember_initial_ports(config: pytest.Config) -> None:
    config._arduino_cli_initial_port = getattr(config.option, "port", None)
    config._arduino_cli_initial_flash_port = getattr(config.option, "flash_port", None)


def _reset_runtime_ports(config: pytest.Config) -> None:
    config.option.port = getattr(config, "_arduino_cli_initial_port", None)
    config.option.flash_port = getattr(config, "_arduino_cli_initial_flash_port", None)


def _set_optional_metadata(config: pytest.Config) -> None:
    try:
        from pytest_metadata.plugin import metadata_key
    except ImportError:
        return

    config.stash[metadata_key]["Profile"] = config.getoption("profile") or "default"


def _ardutest_artifact_dir(config: pytest.Config) -> Path:
    value = Path(config.getoption("arduino_test_artifact_dir"))
    if value.is_absolute():
        return value
    return Path(config.rootpath) / value


def _clean_ardutest_artifacts(config: pytest.Config) -> None:
    if not config.getoption("clean"):
        return

    artifact_dir = _ardutest_artifact_dir(config)
    if not artifact_dir.exists():
        return
    if not artifact_dir.is_dir():
        raise NotADirectoryError(f"ArduTest artifact path is not a directory: {artifact_dir}")
    shutil.rmtree(artifact_dir)


def _request_path(request: pytest.FixtureRequest) -> Path:
    if hasattr(request, "path"):
        return Path(request.path)
    return Path(str(request.fspath))


def _request_has_sketch(request: pytest.FixtureRequest) -> bool:
    test_path = resolve_test_path(_request_path(request))
    return any(test_path.glob("*.ino"))


def _request_uses_peers(request: pytest.FixtureRequest) -> bool:
    return "peers" in getattr(request, "fixturenames", ())


def _peer_dirs(test_path: Path) -> dict[str, Path]:
    peers: dict[str, Path] = {}
    for peer_dir in sorted(test_path.glob("peer_*")):
        if not peer_dir.is_dir():
            continue
        name = peer_dir.name.removeprefix("peer_")
        if not name:
            raise SketchConfigError(f"invalid peer directory name: {peer_dir}")
        if name in peers:
            raise SketchConfigError(f"duplicate peer DUT name: {name}")
        peers[name] = peer_dir
    return peers


def _parse_peer_option(values: list[str], option_name: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values or []:
        if ":" not in value:
            raise pytest.UsageError(f"{option_name} must use NAME:VALUE format: {value}")
        name, option_value = value.split(":", 1)
        if not name or not option_value:
            raise pytest.UsageError(f"{option_name} must use NAME:VALUE format: {value}")
        if name in parsed:
            raise pytest.UsageError(f"{option_name} specified more than once for peer '{name}'")
        parsed[name] = option_value
    return parsed


def _peer_option_map(config: pytest.Config, option_name: str) -> dict[str, str]:
    cache_name = f"_arduino_cli_{option_name}_map"
    cached = getattr(config, cache_name, None)
    if cached is not None:
        return cached
    parsed = _parse_peer_option(config.getoption(option_name), f"--{option_name.replace('_', '-')}")
    setattr(config, cache_name, parsed)
    return parsed


def _validate_peer_option_names(config: pytest.Config, peers: dict[str, Path]) -> None:
    peer_names = set(peers)
    for option_name in ("peer_profile", "peer_port"):
        for name in _peer_option_map(config, option_name):
            if name not in peer_names:
                raise pytest.UsageError(
                    f"--{option_name.replace('_', '-')} specified unknown peer '{name}'"
                )


def _peer_targets_from_request(request: pytest.FixtureRequest) -> list[PeerTarget]:
    test_path = resolve_test_path(_request_path(request))
    peer_dirs = _peer_dirs(test_path)
    _validate_peer_option_names(request.config, peer_dirs)
    peer_profiles = _peer_option_map(request.config, "peer_profile")
    peer_ports = _peer_option_map(request.config, "peer_port")

    targets: list[PeerTarget] = []
    for name, peer_dir in peer_dirs.items():
        try:
            app = ArduinoCliBuildConfig.from_test_path(
                peer_dir,
                profile=peer_profiles.get(name),
                clean=request.config.getoption("clean"),
                allow_single_profile=False,
            )
        except UnsupportedProfileError as e:
            _log_skip(request.config, f"peer {name}: {e}")
            pytest.skip(f"peer {name}: {e}")

        if app.profile is None:
            reason = f"peer {name}: profile is not resolved; set --peer-profile {name}:<profile> or default_profile"
            _log_skip(request.config, reason)
            pytest.skip(reason)

        runtime_port = resolve_peer_port(
            peer=name,
            profile=app.profile,
            option_port=peer_ports.get(name),
            profile_port=app.profile_port,
        )
        if not runtime_port and request.config.getoption("run_mode") != "build":
            reason = f"peer {name}: port is not resolved"
            _log_skip(request.config, reason)
            pytest.skip(reason)

        targets.append(PeerTarget(name=name, app=app, runtime_port=runtime_port))

    return targets


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


def _log_skip(config: pytest.Config, reason: str) -> None:
    if _verbose_level(config) < 1:
        return

    reporter = _terminal_reporter(config)
    if reporter is None:
        return

    reporter.write_line(f"[arduino-cli] skip: {reason}")


@pytest.fixture
def app_path(request: pytest.FixtureRequest) -> str:
    if not _request_has_sketch(request):
        return str(resolve_test_path(_request_path(request)))
    return str(resolve_sketch_dir(_request_path(request)))


@pytest.fixture
def build_dir(request: pytest.FixtureRequest) -> str:
    try:
        arduino_cli_app = _build_config_from_request(request, required=False)
    except UnsupportedProfileError:
        profile = request.config.getoption("profile") or "default"
        return str(resolve_test_path(_request_path(request)) / "build" / profile)
    if arduino_cli_app is None:
        return str(resolve_test_path(_request_path(request)) / "build" / "default")
    return str(arduino_cli_app.build_path)


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
            clean=config.getoption("clean"),
        )
    except UnsupportedProfileError:
        raise
    except SketchConfigError:
        if should_require:
            raise
        return None


def _resolve_build_property(app: ArduinoCliBuildConfig) -> ArduinoCliBuildConfig:
    """Auto-select the injection property for build_config.toml defines/flags.

    Probes ``arduino-cli compile --show-properties`` only when there are flags
    to inject and no explicit override was given. Runs at compile time only.
    """
    if not app.needs_build_property_detection():
        return app
    properties = run_show_properties(app.cli_path, app.sketch_dir, app.profile)
    return app.with_build_property(detect_build_property(properties))


@pytest.fixture(scope="module")
def arduino_cli_app(request: pytest.FixtureRequest) -> ArduinoCliBuildConfig:
    try:
        return _build_config_from_request(request)
    except UnsupportedProfileError as e:
        _log_skip(request.config, str(e))
        pytest.skip(str(e))


@pytest.fixture(scope="module")
def arduino_cli_flasher(
    request: pytest.FixtureRequest,
    arduino_cli_app: ArduinoCliBuildConfig,
) -> ArduinoCliUploadConfig:
    return ArduinoCliUploadConfig.from_build_config(
        arduino_cli_app,
        port=resolve_upload_port(request.config, profile=arduino_cli_app.profile),
    )


@pytest.fixture
def arduino_test(request: pytest.FixtureRequest, dut: Any) -> ArduTestSession:
    return ArduTestSession(
        dut,
        timeout=request.config.getoption("arduino_test_timeout"),
        artifact_dir=_ardutest_artifact_dir(request.config),
        missing_config=request.config.getoption("arduino_test_missing_config"),
    )


@pytest.fixture(scope="module", autouse=True)
def arduino_cli_resolved_port(request: pytest.FixtureRequest) -> None:
    try:
        arduino_cli_app = _build_config_from_request(request, required=False)
    except UnsupportedProfileError as e:
        _log_skip(request.config, str(e))
        pytest.skip(str(e))
    if arduino_cli_app is None:
        return

    _reset_runtime_ports(request.config)

    if getattr(request.config, "_arduino_cli_initial_flash_port", None):
        return
    if getattr(request.config, "_arduino_cli_initial_port", None):
        return

    resolved_port = resolve_port(request.config, profile=arduino_cli_app.profile)
    if not resolved_port and is_socket_url(arduino_cli_app.profile_port):
        resolved_port = arduino_cli_app.profile_port
    if resolved_port:
        request.config.option.port = resolved_port


@pytest.fixture(scope="module", autouse=True)
def arduino_cli_build(
    request: pytest.FixtureRequest,
    arduino_cli_resolved_port: None,
) -> None:
    try:
        arduino_cli_app = _build_config_from_request(request, required=False)
    except UnsupportedProfileError as e:
        _log_skip(request.config, str(e))
        pytest.skip(str(e))
    if arduino_cli_app is None:
        return
    if not _should_build(request.config.getoption("run_mode")):
        return

    # Record profile for state cache
    if arduino_cli_app.profile:
        _set_current_profile(request.config, arduino_cli_app.profile)

    arduino_cli_app = _resolve_build_property(arduino_cli_app)

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
    try:
        arduino_cli_app = _build_config_from_request(request, required=False)
    except UnsupportedProfileError as e:
        _log_skip(request.config, str(e))
        pytest.skip(str(e))
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

    # Record profile for state cache after successful upload
    if arduino_cli_flasher.profile:
        _set_current_profile(request.config, arduino_cli_flasher.profile)

    runtime_port = resolve_port(request.config, profile=arduino_cli_app.profile)
    if socket_url_needs_port_completion(runtime_port):
        request.config.option.port = complete_host_arduino_socket_url(
            runtime_port,
            arduino_cli_app.build_path,
        )
        wait_for_socket_url(request.config.option.port)


def _log_peer_command(
    config: pytest.Config,
    *,
    peer: str,
    action: str,
    command: list[str],
    details: dict[str, str | None],
) -> None:
    peer_details = {"peer": peer, **details}
    _log_command(config, action=f"peer {peer} {action}", command=command, details=peer_details)


def _prepare_peer_targets(request: pytest.FixtureRequest) -> list[PeerTarget]:
    cached = getattr(request.module, "_arduino_cli_peer_targets", None)
    if cached is not None:
        return cached

    targets = _peer_targets_from_request(request)
    run_mode = request.config.getoption("run_mode")

    for target in targets:
        app = target.app
        if _should_build(run_mode):
            app = _resolve_build_property(app)
            _log_peer_command(
                request.config,
                peer=target.name,
                action="compile",
                command=app.build_command(),
                details={
                    "cwd": str(app.sketch_dir),
                    "sketch_dir": str(app.sketch_dir),
                    "build_path": str(app.build_path),
                    "profile": app.profile,
                },
            )
            app.compile()

        if not _should_upload(run_mode):
            continue

        if not app.build_path.is_dir():
            raise FileNotFoundError(
                f"peer {target.name}: build output directory not found: {app.build_path}. "
                "Run with --run-mode=all first, or build the sketch before --run-mode=test."
            )

        flasher = ArduinoCliUploadConfig.from_build_config(
            app,
            port=resolve_peer_upload_port(target.runtime_port),
        )
        _log_peer_command(
            request.config,
            peer=target.name,
            action="upload",
            command=flasher.upload_command(),
            details={
                "cwd": str(flasher.sketch_dir),
                "sketch_dir": str(flasher.sketch_dir),
                "build_path": str(flasher.build_path),
                "profile": flasher.profile,
                "port": flasher.port,
            },
        )
        flasher.upload()

    completed: list[PeerTarget] = []
    for target in targets:
        runtime_port = target.runtime_port
        if _should_upload(run_mode) and socket_url_needs_port_completion(runtime_port):
            runtime_port = complete_host_arduino_socket_url(runtime_port, target.app.build_path)
            wait_for_socket_url(runtime_port)
        completed.append(PeerTarget(name=target.name, app=target.app, runtime_port=runtime_port))

    request.module._arduino_cli_peer_targets = completed
    return completed


def _make_peer_dut(request: pytest.FixtureRequest, target: PeerTarget) -> tuple[Any, Callable[[], None]]:
    if not target.runtime_port:
        raise RuntimeError(f"peer {target.name}: runtime port is not resolved")

    from pytest_embedded.app import App
    from pytest_embedded.plugin import _listener_gn, _pexpect_fr_gn, pexpect_proc_fn
    from pytest_embedded_serial.dut import SerialDut
    from pytest_embedded_serial.serial import Serial

    manager = request.getfixturevalue("_mp_manager")
    meta = request.getfixturevalue("_meta")
    test_case_tempdir = Path(request.getfixturevalue("test_case_tempdir"))
    logfile_extension = request.getfixturevalue("logfile_extension")
    with_timestamp = request.getfixturevalue("with_timestamp")
    baud = int(request.config.getoption("baud") or Serial.DEFAULT_BAUDRATE)

    msg_queue = manager.MessageQueue()
    logfile = str(test_case_tempdir / f"peer-{target.name}{logfile_extension}")
    listener = _listener_gn(
        msg_queue,
        logfile,
        with_timestamp,
        0,
        0,
    )
    pexpect_fr = _pexpect_fr_gn(logfile, listener)
    pexpect_proc = pexpect_proc_fn(pexpect_fr)
    app = App(app_path=str(target.app.sketch_dir), build_dir=str(target.app.build_path))
    serial = Serial(msg_queue=msg_queue, port=target.runtime_port, baud=baud, meta=meta)
    dut = SerialDut(
        pexpect_proc=pexpect_proc,
        msg_queue=msg_queue,
        app=app,
        pexpect_logfile=logfile,
        test_case_name=request.node.name,
        meta=meta,
        serial=serial,
    )

    def cleanup() -> None:
        try:
            dut.close()
        finally:
            try:
                serial.close()
            finally:
                try:
                    pexpect_fr.close()
                finally:
                    if listener.is_alive():
                        listener.terminate()
                        listener.join(timeout=5)
                    listener.close()

    return dut, cleanup


@pytest.fixture
def peers(request: pytest.FixtureRequest) -> PeerDutMap:
    targets = _prepare_peer_targets(request)
    if request.config.getoption("run_mode") == "build":
        yield PeerDutMap()
        return

    peer_map: PeerDutMap = PeerDutMap()
    cleanups: list[Callable[[], None]] = []
    try:
        for target in targets:
            dut, cleanup = _make_peer_dut(request, target)
            peer_map[target.name] = dut
            cleanups.append(cleanup)
        yield peer_map
    finally:
        for cleanup in reversed(cleanups):
            cleanup()


@pytest.fixture(autouse=True)
def skip_test_execution_in_build_mode(
    request: pytest.FixtureRequest,
    arduino_cli_build: None,
) -> None:
    if request.config.getoption("run_mode") == "build":
        if _request_uses_peers(request):
            request.getfixturevalue("peers")
        pytest.skip("skipped test execution in build-only mode")


def _initialize_state_cache(config: pytest.Config) -> None:
    """Initialize state cache if --save-state is enabled."""
    # Save config globally for use in pytest_runtest_logreport
    globals()["_GLOBAL_CONFIG"] = config

    if not config.getoption("save_state"):
        config._arduino_cli_state_cache = None
        return

    save_dir_opt = config.getoption("save_state_dir")
    if Path(save_dir_opt).is_absolute():
        save_dir = Path(save_dir_opt)
    else:
        save_dir = Path(config.rootpath) / save_dir_opt

    cache = StateCache(save_dir)
    cache.ensure_dir_exists()
    config._arduino_cli_state_cache = cache
    globals()["_GLOBAL_STATE_CACHE"] = cache


_GLOBAL_STATE_CACHE: StateCache | None = None
_GLOBAL_CONFIG: pytest.Config | None = None
# Pending updates collected during the test session. Each item is (profile, nodeid, result)
_PENDING_STATE_UPDATES: list[tuple[str, str, str]] = []

def _get_state_cache(config: pytest.Config) -> StateCache | None:
    """Get state cache from config, or None if not enabled.

    Falls back to a process-global cache if set (robust across config instances).
    """
    cache = getattr(config, "_arduino_cli_state_cache", None)
    if cache is not None:
        return cache
    return globals().get("_GLOBAL_STATE_CACHE")


def _get_current_profile(config: pytest.Config) -> str | None:
    """Get the profile that was used for the current test run."""
    return getattr(config, "_arduino_cli_current_profile", None)


def _set_current_profile(config: pytest.Config, profile: str | None) -> None:
    """Record the profile being used for the current test run."""
    config._arduino_cli_current_profile = profile


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Capture test results and update state cache on test completion."""
    # Only process call phase (actual test execution)
    if report.when != "call":
        return

    # Skip if test was skipped or not run
    if report.outcome == "skipped":
        return

    # Get config from report; be robust across pytest versions
    config = getattr(report, "config", None)
    if config is None:
        pyfuncitem = getattr(report, "_pyfuncitem", None)
        if pyfuncitem is not None:
            config = getattr(pyfuncitem, "config", None)
    if config is None:
        session = getattr(report, "session", None)
        if session is not None:
            config = getattr(session, "config", None)
    if config is None:
        # Fallback to global config set during pytest_configure
        config = globals().get("_GLOBAL_CONFIG")
    if config is None:
        # Unable to determine config, skip state update
        return

    # Determine profile: prefer recorded one, fall back to CLI option
    profile = _get_current_profile(config) or config.getoption("profile")
    if profile is None:
        return

    # Get state cache
    cache = _get_state_cache(config)
    if cache is None:
        # Attempt to initialize a cache from config options if save_state was enabled
        try:
            if config.getoption("save_state"):
                save_dir_opt = config.getoption("save_state_dir")
                if Path(save_dir_opt).is_absolute():
                    save_dir = Path(save_dir_opt)
                else:
                    save_dir = Path(config.rootpath) / save_dir_opt
                cache = StateCache(save_dir)
                cache.ensure_dir_exists()
                config._arduino_cli_state_cache = cache
                globals()["_GLOBAL_STATE_CACHE"] = cache
        except Exception:
            pass
    if cache is None:
        return

    # Collect pending update to apply at session finish
    try:
        nodeid = report.nodeid
        if report.outcome == "passed":
            result = "passed"
        elif report.outcome == "failed":
            result = "failed"
        else:
            result = report.outcome
        _PENDING_STATE_UPDATES.append((profile, nodeid, result))
    except Exception:
        pass


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Apply pending state cache updates at session end and persist state.json."""
    try:
        config = getattr(session, "config", None)
        if config is None:
            return
        if not config.getoption("save_state"):
            return

        save_dir_opt = config.getoption("save_state_dir")
        if Path(save_dir_opt).is_absolute():
            save_dir = Path(save_dir_opt)
        else:
            save_dir = Path(config.rootpath) / save_dir_opt

        cache = StateCache(save_dir)
        cache.ensure_dir_exists()
        state = cache.load_state()

        # Apply pending updates
        for profile, nodeid, result in _PENDING_STATE_UPDATES:
            try:
                cache.update_test_result(state, profile, nodeid, result)
            except Exception:
                continue

        # Save the consolidated state
        cache.save_state(state)
    except Exception:
        pass
