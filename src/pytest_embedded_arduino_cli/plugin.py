from __future__ import annotations

from dataclasses import dataclass
from contextlib import ExitStack
from pathlib import Path
import shutil
import shlex
from typing import Any, Callable
from types import SimpleNamespace

import pytest

from . import combination as combinations
from .ardutest import ArduTestSession
from .app import (
    ArduinoCliBuildConfig,
    SketchConfigError,
    UnsupportedProfileError,
    detect_build_properties,
    load_sketch_yaml,
    resolve_sketch_dir,
    resolve_test_path,
    run_show_properties,
)
from .device_lock import DeviceLockError, DeviceLockInfo, DeviceLockSet, default_lock_dir, normalize_device_key
from .flasher import ArduinoCliUploadConfig
from .log_summary import LogSummaryCollector
from .monitor import MonitorTarget, is_monitor_url, own_monitor_protocols, port_protocol, register_protocol_handler
from .serial import (
    complete_host_arduino_socket_url,
    ensure_default_embedded_services,
    install_fast_socket_redirect_thread,
    is_socket_url,
    peer_port_env_names,
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
    group.addoption("--profiles", help="Primary profile list (comma-separated), or all. Opts into combination execution.")
    group.addoption("--peer-profiles", action="append", default=[], metavar="all|NAME:PROFILES",
                    help="All peers' profiles, or a named peer's list/all. Repeat for different peers.")
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
        "--device-lock",
        action="store",
        choices=("auto", "off", "required"),
        default="auto",
        help="Control physical device locking before upload.",
    )
    group.addoption(
        "--device-lock-timeout",
        action="store",
        type=float,
        default=300.0,
        help="Seconds to wait for a physical device lock.",
    )
    group.addoption(
        "--device-lock-dir",
        action="store",
        default=None,
        help="Directory for device lock files. Defaults to a user runtime/cache directory.",
    )
    group.addoption(
        "--device-lock-key",
        action="store",
        default=None,
        help="Override the primary DUT device lock key.",
    )
    group.addoption(
        "--arduino-cli-no-log-summary",
        action="store_true",
        default=False,
        help="Do not write result marker files (PASSED.txt/FAILED.txt, SUMMARY.txt) into the pytest-embedded log dir.",
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
        f"arduino-cli profile: {config.getoption('profiles') or config.getoption('profile') or 'default'}",
        *([f"arduino-cli peer profiles: {config.getoption('peer_profiles')}"] if config.getoption('peer_profiles') else []),
    ]


def pytest_configure(config: pytest.Config) -> None:
    combinations.configure(config)
    # Entry-point discovery order must not determine whether pytest-embedded
    # or this plugin supplies the Arduino paths and per-configuration log name.
    config.pluginmanager.register(_EmbeddedFixtures(), "arduino-cli-fixture-overrides")
    _PENDING_STATE_UPDATES.clear()
    globals()["_GLOBAL_STATE_CACHE"] = None
    install_fast_socket_redirect_thread()
    register_protocol_handler()
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

    if metadata_key in config.stash:
        config.stash[metadata_key]["Profile"] = getattr(config.option, "profiles", None) or config.getoption("profile") or "default"
        if getattr(config.option, "peer_profiles", None):
            config.stash[metadata_key]["Peer profiles"] = config.option.peer_profiles


def _ardutest_artifact_dir(config: pytest.Config) -> Path:
    value = Path(config.getoption("arduino_test_artifact_dir"))
    if value.is_absolute():
        return value
    return Path(config.rootpath) / value


def _clean_ardutest_artifacts(config: pytest.Config) -> None:
    if not config.getoption("clean") or getattr(config.option, "collectonly", False):
        return

    artifact_dir = _ardutest_artifact_dir(config)
    if not artifact_dir.exists():
        return
    if not artifact_dir.is_dir():
        raise NotADirectoryError(f"ArduTest artifact path is not a directory: {artifact_dir}")
    shutil.rmtree(artifact_dir)


def pytest_addhooks(pluginmanager) -> None:
    pluginmanager.add_hookspecs(combinations.Hooks)


def pytest_generate_tests(metafunc) -> None:
    if not combinations.enabled(metafunc.config):
        return
    path = Path(metafunc.definition.path)
    if not any(path.parent.glob("*.ino")):
        return
    plans = combinations.plans(metafunc.config, path, "peers" in metafunc.fixturenames)
    metafunc.parametrize(
        "_arduino_cli_plan",
        [pytest.param(plan, id=plan.combination.id,
                      marks=[pytest.mark.skip(reason="; ".join(plan.skip_reasons))] if plan.skip_reasons else [])
         for plan in plans],
        indirect=True, scope="module",
    )


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_collection_modifyitems(config, items):
    combinations.validate_selection(config)
    yield
    # Evaluate applicability only on selected items, after -k/-m/--lf filtering.
    for item in items:
        plan = getattr(item, "callspec", None)
        plan = plan.params.get("_arduino_cli_plan") if plan is not None else None
        combination = plan.combination if plan else combinations.legacy_combination(item)
        item.stash[combinations.COMBINATION] = combination
        if plan:
            conflicts = {"port", "flash_port", "app_path", "build_dir"} & item.callspec.params.keys()
            if conflicts:
                raise pytest.UsageError(
                    f"{item.nodeid}: combination mode owns {', '.join(sorted(conflicts))}; "
                    "use profile configuration instead of parametrizing these fixtures"
                )
            item.stash[combinations.PLAN] = plan
        combinations.apply_skip_rules(item, combination)
    config.stash[combinations.PLANNED] = [item.nodeid for item in items]


def pytest_report_collectionfinish(config, items):
    if not config.option.collectonly:
        return
    return [f"[arduino-cli] SKIP {item.nodeid}: {marker.kwargs.get('reason', 'skipped')}"
            for item in items for marker in item.iter_markers("skip")
            if item.stash.get(combinations.PLAN, None) or item.stash.get(combinations.RULE_REASONS, ())]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    report.config = item.config
    combination = item.stash.get(combinations.COMBINATION, None)
    report.arduino_profile = combination.primary if combination else None
    report.arduino_peers = dict(combination.peers) if combination else {}
    plan = item.stash.get(combinations.PLAN, None)
    report.arduino_log_dir = combinations.artifact_name(item.nodeid) if plan else item.name
    report.arduino_combination_mode = plan is not None
    if combination:
        report.user_properties.extend([
            ("arduino.primary", combination.primary or ""),
            *[(f"arduino.peer.{name}", profile or "") for name, profile in combination.peers.items()],
        ])
    if report.when == "call":
        item._arduino_cli_call_result = report.outcome
    report.arduino_verification_result = None
    if report.when == "teardown":
        result = getattr(item, "_arduino_cli_call_result", None)
        state = item.funcargs.get("_arduino_cli_context", item.module if hasattr(item, "module") else None)
        if combination and getattr(state, "_arduino_cli_uploaded", False) and result in ("passed", "failed"):
            report.arduino_verification_result = "error" if report.failed else result
        if report.failed and plan:
            item.session.shouldstop = "Arduino combination cleanup failed; refusing to reuse hardware"


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not combinations.enabled(config) or config.option.collectonly:
        return
    collector = getattr(config, "_arduino_cli_log_summary", None)
    if collector is not None:
        completed = collector.completed_nodeids()
    else:
        completed = getattr(config, "_arduino_cli_completed", set())
    planned = config.stash.get(combinations.PLANNED, [])
    pending = [nodeid for nodeid in planned if nodeid not in completed]
    terminalreporter.write_line(
        f"Arduino selection: {len(planned)} planned items, {len(set(planned) & completed)} finished (including skips), "
        f"{len(pending)} unfinished"
    )
    for nodeid in pending:
        terminalreporter.write_line(f"  unfinished: {nodeid}")


@pytest.fixture(scope="module")
def _arduino_cli_plan(request):
    return getattr(request, "param", None)


@pytest.fixture(scope="module")
def _arduino_cli_context(request, _arduino_cli_plan):
    # An explicit dependency ensures *all* module resources expire on a
    # parameter change, including requests that resolve fixtures dynamically.
    state = SimpleNamespace() if _arduino_cli_plan else request.module
    yield state
    if _arduino_cli_plan:
        _reset_runtime_ports(request.config)


def _plan_from_request(request):
    if not combinations.enabled(request.config):
        return None
    return request.getfixturevalue("_arduino_cli_plan")


def _runtime_state(request):
    if not combinations.enabled(request.config):
        return request.module
    return request.getfixturevalue("_arduino_cli_context")


@pytest.fixture
def test_case_name(request):
    if request.node.stash.get(combinations.PLAN, None):
        return combinations.artifact_name(request.node.nodeid)
    return request.node.name


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


def _peer_targets_from_request(
    request: pytest.FixtureRequest,
    *,
    require_ports: bool = True,
    strict: bool = True,
) -> list[PeerTarget]:
    test_path = resolve_test_path(_request_path(request))
    peer_dirs = _peer_dirs(test_path)
    plan = _plan_from_request(request)
    if plan:
        peer_dirs = {name: directory for name, directory in peer_dirs.items() if name in plan.combination.peers}
    else:
        _validate_peer_option_names(request.config, peer_dirs)
    peer_profiles = _peer_option_map(request.config, "peer_profile")
    peer_ports = _peer_option_map(request.config, "peer_port")

    targets: list[PeerTarget] = []
    for name, peer_dir in peer_dirs.items():
        try:
            app = ArduinoCliBuildConfig.from_test_path(
                peer_dir,
                profile=plan.combination.peers[name] if plan else peer_profiles.get(name),
                clean=request.config.getoption("clean"),
                allow_single_profile=False,
            )
        except UnsupportedProfileError as e:
            _log_skip(request.config, f"peer {name}: {e}")
            if strict:
                pytest.skip(f"peer {name}: {e}")
            continue

        if app.profile is None:
            reason = f"peer {name}: profile is not resolved; set --peer-profile {name}:<profile> or default_profile"
            _log_skip(request.config, reason)
            if strict:
                pytest.skip(reason)
            continue

        runtime_port = resolve_peer_port(
            peer=name,
            profile=app.profile,
            option_port=peer_ports.get(name),
            profile_port=app.profile_port,
            allow_common=not plan or f"peer:{name}" not in plan.multiple_roles,
        )
        if not runtime_port and require_ports:
            reason = f"peer {name}: port is not resolved"
            _log_skip(request.config, reason)
            pytest.skip(reason)

        targets.append(PeerTarget(name=name, app=app, runtime_port=runtime_port))

    _check_peer_env_names(peer_dirs, targets)
    return targets


def _check_peer_env_names(peer_dirs: dict[str, Path], targets: list[PeerTarget]) -> None:
    """Reject peers whose port variables collide, such as ``peer_a_b`` with
    profile ``c`` and ``peer_a`` with profile ``b_c``."""
    profiles = {target.name: target.app.profile for target in targets}
    owners: dict[str, str] = {}
    for name in peer_dirs:
        for env_name in peer_port_env_names(name, profiles.get(name)):
            owner = owners.setdefault(env_name, name)
            if owner != name:
                raise SketchConfigError(
                    f"peers '{owner}' and '{name}' share the port variable {env_name}; rename one of them"
                )


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


def _device_lock_dir(config: pytest.Config) -> Path:
    value = config.getoption("device_lock_dir")
    if value:
        return Path(value).expanduser().resolve()
    return default_lock_dir()


def _device_lock_enabled(config: pytest.Config) -> bool:
    return config.getoption("device_lock") != "off"


def _is_lockable_port(port: str | None) -> bool:
    return bool(port and not is_socket_url(port))


def _primary_device_lock_info(
    config: pytest.Config,
    app: ArduinoCliBuildConfig,
    upload_port: str | None,
) -> DeviceLockInfo | None:
    mode = config.getoption("device_lock")
    if mode == "off":
        return None

    override = config.getoption("device_lock_key")
    runtime_port = resolve_port(config, profile=app.profile)
    key = override
    port = upload_port if _is_lockable_port(upload_port) else runtime_port
    if key is None and _is_lockable_port(upload_port):
        key = upload_port
    if key is None and _is_lockable_port(runtime_port):
        key = runtime_port

    if key is None:
        if mode == "required":
            raise pytest.UsageError("device lock is required, but no primary physical serial port was resolved")
        return None

    return DeviceLockInfo(
        key=key,
        port=port,
        profile=app.profile,
        sketch_dir=str(app.sketch_dir),
        role="primary",
    )


def _peer_device_lock_infos(targets: list[PeerTarget]) -> list[DeviceLockInfo]:
    infos: list[DeviceLockInfo] = []
    for target in targets:
        if not _is_lockable_port(target.runtime_port):
            continue
        infos.append(
            DeviceLockInfo(
                key=str(target.runtime_port),
                port=target.runtime_port,
                profile=target.app.profile,
                sketch_dir=str(target.app.sketch_dir),
                role=f"peer:{target.name}",
            )
        )
    return infos


def _acquire_device_locks(
    config: pytest.Config,
    infos: list[DeviceLockInfo],
) -> DeviceLockSet | None:
    if not infos or not _device_lock_enabled(config):
        return None

    primary_key = getattr(config, "_arduino_cli_primary_device_lock_key", None)
    if primary_key is not None:
        for info in infos:
            if info.key == primary_key:
                raise pytest.UsageError(f"duplicate device lock key already used by primary DUT: {info.key}")

    try:
        lock_set = DeviceLockSet(
            infos,
            lock_dir=_device_lock_dir(config),
            timeout=config.getoption("device_lock_timeout"),
        )
        lock_set.acquire()
    except (DeviceLockError, ValueError) as e:
        raise pytest.UsageError(str(e)) from e
    return lock_set


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


class _EmbeddedFixtures:
    app_path = staticmethod(app_path)
    build_dir = staticmethod(build_dir)
    skip_autoflash = staticmethod(skip_autoflash)
    test_case_name = staticmethod(test_case_name)


def _build_config_from_request(
    request: pytest.FixtureRequest,
    *,
    required: bool = True,
) -> ArduinoCliBuildConfig | None:
    config = request.config
    plan = _plan_from_request(request)
    should_require = required or _request_has_sketch(request)
    try:
        return ArduinoCliBuildConfig.from_test_path(
            _request_path(request),
            profile=plan.combination.primary if plan else config.getoption("profile"),
            clean=config.getoption("clean"),
        )
    except UnsupportedProfileError:
        raise
    except SketchConfigError:
        if should_require:
            raise
        return None


def _show_properties(config: pytest.Config, app: ArduinoCliBuildConfig) -> dict[str, str]:
    """``arduino-cli compile --show-properties``, run once per sketch and profile."""
    cache = getattr(config, "_arduino_cli_show_properties", None)
    if cache is None:
        cache = {}
        config._arduino_cli_show_properties = cache
    key = (str(app.sketch_dir), app.profile)
    if key not in cache:
        cache[key] = run_show_properties(app.cli_path, app.sketch_dir, app.profile)
    return cache[key]


def _board_key(app: ArduinoCliBuildConfig) -> tuple[str, ...]:
    """What decides the platform's monitor: the profile's fqbn and platforms.

    Sketches whose profiles name the same board share one probe. Without a
    profile, each sketch is probed on its own.
    """
    if app.profile is None:
        return ("sketch", str(app.sketch_dir))
    profiles = load_sketch_yaml(app.sketch_yaml).get("profiles") or {}
    profile_data = profiles.get(app.profile)
    if not isinstance(profile_data, dict):
        return ("sketch", str(app.sketch_dir), app.profile)
    return ("board", repr(profile_data.get("fqbn")), repr(profile_data.get("platforms")))


def _platform_has_own_monitor(config: pytest.Config, app: ArduinoCliBuildConfig, protocol: str) -> bool:
    cache = getattr(config, "_arduino_cli_own_monitor", None)
    if cache is None:
        cache = {}
        config._arduino_cli_own_monitor = cache
    key = _board_key(app)
    if key not in cache:
        cache[key] = own_monitor_protocols(_show_properties(config, app))
    return protocol in cache[key]


def _runtime_port_for_app(
    config: pytest.Config,
    app: ArduinoCliBuildConfig,
    port: str | None,
) -> str | None:
    """Route a runtime port through ``arduino-cli monitor`` when the platform
    brings its own pluggable monitor for the port's protocol.

    A plain path is the ``serial`` protocol. A URL such as ``wchlink://...``
    is routed when the platform has a monitor for ``wchlink``; other URLs are
    left to pyserial. ``socket://`` (the host core) is never probed.
    """
    if not port or is_monitor_url(port) or is_socket_url(port):
        return port
    protocol = port_protocol(port)
    if not _platform_has_own_monitor(config, app, protocol):
        return port
    return MonitorTarget(
        address=port,
        sketch_dir=app.sketch_dir,
        profile=app.profile,
        cli_path=app.cli_path,
        protocol=protocol,
    ).to_url()


def _resolve_build_property(config: pytest.Config, app: ArduinoCliBuildConfig) -> ArduinoCliBuildConfig:
    """Auto-select the injection property for build_config.toml defines/flags.

    Probes ``arduino-cli compile --show-properties`` only when there are flags
    to inject and no explicit override was given. Runs at compile time only.
    """
    if not app.needs_build_property_detection():
        return app
    properties = _show_properties(config, app)
    return app.with_build_properties(detect_build_properties(properties))


@pytest.fixture(scope="module")
def arduino_cli_app(request: pytest.FixtureRequest, _arduino_cli_context) -> ArduinoCliBuildConfig:
    try:
        return _build_config_from_request(request)
    except UnsupportedProfileError as e:
        _log_skip(request.config, str(e))
        pytest.skip(str(e))


@pytest.fixture(scope="module")
def arduino_cli_build_properties(
    request: pytest.FixtureRequest,
    arduino_cli_app: ArduinoCliBuildConfig,
) -> dict[str, str]:
    """The expanded build properties of the sketch and profile under test."""
    return dict(_show_properties(request.config, arduino_cli_app))


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
    artifact_dir = _ardutest_artifact_dir(request.config)
    if request.node.stash.get(combinations.PLAN, None):
        artifact_dir /= combinations.artifact_name(request.node.nodeid)
    return ArduTestSession(
        dut,
        timeout=request.config.getoption("arduino_test_timeout"),
        artifact_dir=artifact_dir,
        missing_config=request.config.getoption("arduino_test_missing_config"),
    )


@pytest.fixture(scope="module", autouse=True)
def arduino_cli_resolved_port(request: pytest.FixtureRequest, _arduino_cli_context) -> None:
    try:
        arduino_cli_app = _build_config_from_request(request, required=False)
    except UnsupportedProfileError as e:
        _log_skip(request.config, str(e))
        pytest.skip(str(e))
    if arduino_cli_app is None:
        return

    _reset_runtime_ports(request.config)

    plan = _plan_from_request(request)
    resolved_port = resolve_port(request.config, profile=arduino_cli_app.profile,
                                 allow_common=not plan or "primary" not in plan.multiple_roles)
    if not resolved_port:
        resolved_port = arduino_cli_app.profile_port
    if resolved_port:
        request.config.option.port = resolved_port
    if plan and request.config.getoption("run_mode") != "build":
        if not resolved_port:
            pytest.skip(f"{plan.combination.id}: primary port is not resolved")
        targets = _peer_targets_from_request(request)
        _check_combination_devices(request, resolved_port, targets)


def _check_combination_devices(request, primary_port, targets) -> None:
    owners = {}
    ports = [("primary", primary_port), ("primary", request.config.getoption("flash_port"))]
    ports.extend((f"peer {target.name}", target.runtime_port) for target in targets)
    for role, port in ports:
        if not port or is_socket_url(port):
            continue
        if is_monitor_url(port):
            port = MonitorTarget.from_url(port).address
        key = normalize_device_key(port)
        previous = owners.setdefault(key, role)
        if previous != role:
            pytest.skip(f"duplicate device: {previous} and {role} use {key}")


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

    arduino_cli_app = _resolve_build_property(request.config, arduino_cli_app)

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
    _compile_peer_targets(request)


@pytest.fixture(scope="module", autouse=True)
def arduino_cli_device_locks(request: pytest.FixtureRequest, _arduino_cli_context) -> None:
    yield
    state = _runtime_state(request)
    with ExitStack() as cleanup:
        for name in ("_arduino_cli_primary_device_lock_set", "_arduino_cli_peer_device_lock_set"):
            lock_set = getattr(state, name, None)
            if lock_set is not None:
                cleanup.callback(lock_set.release)
            if hasattr(state, name):
                delattr(state, name)
        if hasattr(request.config, "_arduino_cli_primary_device_lock_key"):
            delattr(request.config, "_arduino_cli_primary_device_lock_key")
        if hasattr(state, "_arduino_cli_peer_device_lock_ready"):
            delattr(state, "_arduino_cli_peer_device_lock_ready")


@pytest.fixture(scope="module", autouse=True)
def arduino_cli_upload(
    request: pytest.FixtureRequest,
    arduino_cli_build: None,
    arduino_cli_resolved_port: None,
    arduino_cli_device_locks: None,
) -> None:
    run_mode = request.config.getoption("run_mode")
    if not _should_upload(run_mode):
        yield
        return
    try:
        arduino_cli_app = _build_config_from_request(request, required=False)
    except UnsupportedProfileError as e:
        _log_skip(request.config, str(e))
        pytest.skip(str(e))
    if arduino_cli_app is None:
        yield
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

    lock_info = _primary_device_lock_info(
        request.config,
        arduino_cli_app,
        arduino_cli_flasher.port,
    )
    plan = _plan_from_request(request)
    state = _runtime_state(request)
    infos = [lock_info] if lock_info else []
    if plan:
        targets = _peer_targets_from_request(request)
        peer_infos = _peer_device_lock_infos(targets)
        if targets and not peer_infos and request.config.getoption("device_lock") == "required":
            raise pytest.UsageError("device lock is required, but no peer physical serial port was resolved")
        infos.extend(peer_infos)
    lock_set = _acquire_device_locks(request.config, infos)
    state._arduino_cli_primary_device_lock_set = lock_set
    if plan:
        state._arduino_cli_peer_device_lock_ready = True
    if lock_info is not None:
        request.config._arduino_cli_primary_device_lock_key = lock_info.key

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
    state._arduino_cli_uploaded = True

    runtime_port = resolve_port(request.config, profile=arduino_cli_app.profile)
    if socket_url_needs_port_completion(runtime_port):
        request.config.option.port = complete_host_arduino_socket_url(
            runtime_port,
            arduino_cli_app.build_path,
        )
        wait_for_socket_url(request.config.option.port)
    _route_runtime_port_through_monitor(request.config, arduino_cli_app)
    yield


def _route_runtime_port_through_monitor(config: pytest.Config, app: ArduinoCliBuildConfig) -> None:
    port = getattr(config.option, "port", None)
    monitor_port = _runtime_port_for_app(config, app, port)
    if monitor_port == port:
        return
    config.option.port = monitor_port
    target = MonitorTarget.from_url(monitor_port)
    _log_command(
        config,
        action="monitor",
        command=target.command(),
        details={
            "cwd": str(target.sketch_dir),
            "profile": target.profile,
            "port": target.address,
        },
    )


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


def _compile_peer_targets(request: pytest.FixtureRequest) -> list[PeerTarget]:
    cached = getattr(_runtime_state(request), "_arduino_cli_peer_compile_targets", None)
    if cached is not None:
        return cached

    run_mode = request.config.getoption("run_mode")
    if not _should_build(run_mode):
        _runtime_state(request)._arduino_cli_peer_compile_targets = []
        _runtime_state(request)._arduino_cli_peer_compiled_names = set()
        return []

    targets = _peer_targets_from_request(request, require_ports=False, strict=False)
    compiled_names: set[str] = set()
    for target in targets:
        app = _resolve_build_property(request.config, target.app)
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
        compiled_names.add(target.name)

    _runtime_state(request)._arduino_cli_peer_compile_targets = targets
    _runtime_state(request)._arduino_cli_peer_compiled_names = compiled_names
    return targets


def _prepare_peer_targets(request: pytest.FixtureRequest) -> list[PeerTarget]:
    cached = getattr(_runtime_state(request), "_arduino_cli_peer_targets", None)
    if cached is not None:
        _lock_peer_targets_for_request(request, cached)
        return cached

    targets = _peer_targets_from_request(
        request,
        require_ports=request.config.getoption("run_mode") != "build",
        strict=True,
    )
    run_mode = request.config.getoption("run_mode")
    compiled_names = getattr(_runtime_state(request), "_arduino_cli_peer_compiled_names", set())

    for target in targets:
        app = target.app
        if _should_build(run_mode) and target.name not in compiled_names:
            app = _resolve_build_property(request.config, app)
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
            compiled_names.add(target.name)

    _runtime_state(request)._arduino_cli_peer_compiled_names = compiled_names

    if not _should_upload(run_mode):
        _runtime_state(request)._arduino_cli_peer_targets = targets
        return targets

    for target in targets:
        app = target.app
        if not app.build_path.is_dir():
            raise FileNotFoundError(
                f"peer {target.name}: build output directory not found: {app.build_path}. "
                "Run with --run-mode=all first, or build the sketch before --run-mode=test."
            )

    _lock_peer_targets_for_request(request, targets)

    for target in targets:
        app = target.app
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

    _runtime_state(request)._arduino_cli_peer_targets = completed
    return completed


def _lock_peer_targets_for_request(
    request: pytest.FixtureRequest,
    targets: list[PeerTarget],
) -> None:
    if request.config.getoption("run_mode") == "build":
        return
    if getattr(_runtime_state(request), "_arduino_cli_peer_device_lock_ready", False):
        return

    infos = _peer_device_lock_infos(targets)
    if request.config.getoption("device_lock") == "required" and not infos and targets:
        raise pytest.UsageError("device lock is required, but no peer physical serial port was resolved")

    lock_set = _acquire_device_locks(request.config, infos)
    _runtime_state(request)._arduino_cli_peer_device_lock_set = lock_set
    _runtime_state(request)._arduino_cli_peer_device_lock_ready = True


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
    def close_listener(listener):
        if listener.is_alive():
            listener.terminate()
            listener.join(timeout=5)
        listener.close()

    with ExitStack() as resources:
        listener = _listener_gn(msg_queue, logfile, with_timestamp, 0, 0)
        resources.callback(close_listener, listener)
        pexpect_fr = _pexpect_fr_gn(logfile, listener)
        resources.callback(pexpect_fr.close)
        pexpect_proc = pexpect_proc_fn(pexpect_fr)
        app = App(app_path=str(target.app.sketch_dir), build_dir=str(target.app.build_path))
        runtime_port = _runtime_port_for_app(request.config, target.app, target.runtime_port)
        serial = Serial(msg_queue=msg_queue, port=runtime_port, baud=baud, meta=meta)
        resources.callback(serial.close)
        dut = SerialDut(
            pexpect_proc=pexpect_proc,
            msg_queue=msg_queue,
            app=app,
            pexpect_logfile=logfile,
            test_case_name=request.node.name,
            meta=meta,
            serial=serial,
        )
        resources.callback(dut.close)
        cleanup = resources.pop_all()
        return dut, cleanup.close


@pytest.fixture
def peers(request: pytest.FixtureRequest) -> PeerDutMap:
    plan = _plan_from_request(request)
    if plan and not plan.combination.peers and _peer_dirs(resolve_test_path(_request_path(request))):
        raise pytest.UsageError("declare a peers fixture dependency for combination collection; dynamic getfixturevalue('peers') is unsupported")
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
        with ExitStack() as stack:
            for cleanup in cleanups:
                stack.callback(cleanup)


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

    if not config.getoption("save_state") or getattr(config.option, "collectonly", False):
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


def _config_from_report(report: pytest.TestReport) -> pytest.Config | None:
    """Get config from a report; be robust across pytest versions."""
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
    return config


def _get_log_summary_collector(config: pytest.Config) -> LogSummaryCollector | None:
    """Get the log summary collector, unless --arduino-cli-no-log-summary was given."""
    try:
        if config.getoption("arduino_cli_no_log_summary"):
            return None
    except Exception:
        return None

    collector = getattr(config, "_arduino_cli_log_summary", None)
    if collector is None:
        collector = LogSummaryCollector()
        config._arduino_cli_log_summary = collector
    return collector


def _session_tempdir(config: pytest.Config) -> Path | None:
    """Locate the log dir pytest-embedded created for this session, if any."""
    try:
        from pytest_embedded.plugin import _session_tempdir_key
    except Exception:
        return None

    tempdir = config.stash.get(_session_tempdir_key, None)
    if not tempdir:
        return None
    path = Path(tempdir)
    return path if path.is_dir() else None


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Capture test results and update state cache on test completion."""
    config = _config_from_report(report)

    # Every phase feeds the log summary: setup failures are where build and upload
    # errors land, and skips are worth showing in the tree too.
    if config is not None:
        collector = _get_log_summary_collector(config)
        if collector is not None:
            try:
                collector.record(report, getattr(report, "arduino_profile", None))
            except Exception:
                pass

    if config is None:
        # Unable to determine config, skip state update
        return

    if report.when == "teardown":
        completed = getattr(config, "_arduino_cli_completed", set())
        completed.add(report.nodeid)
        config._arduino_cli_completed = completed
    result = getattr(report, "arduino_verification_result", None)
    if result is None:
        return
    profile = getattr(report, "arduino_profile", None)
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
        _PENDING_STATE_UPDATES.append((profile, nodeid, result))
    except Exception:
        pass


def _write_log_summary(session: pytest.Session, exitstatus: int) -> None:
    """Drop result marker files into the pytest-embedded log dir. Never fatal."""
    try:
        config = getattr(session, "config", None)
        if config is None:
            return
        collector = getattr(config, "_arduino_cli_log_summary", None)
        if collector is None:
            return
        session_tempdir = _session_tempdir(config)
        if session_tempdir is None:
            # No DUT was created, so pytest-embedded never made a log dir.
            return
        collector.write(session_tempdir, session, exitstatus)
    except Exception:
        pass


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write the log summary and persist pending state cache updates at session end."""
    _write_log_summary(session, exitstatus)
    if session.config.option.collectonly:
        return

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
