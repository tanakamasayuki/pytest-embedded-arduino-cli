"""End-to-end collection and lifecycle tests; hardware operations are recorded fakes."""
from pathlib import Path
import json
import re
import textwrap
import xml.etree.ElementTree as ET

import pytest
import yaml


HARDWARE = '''
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
import pytest_embedded_arduino_cli.plugin as plugin
from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.flasher import ArduinoCliUploadConfig

ROOT = Path(__file__).parent

def record(*event):
    with (ROOT / "events.jsonl").open("a") as f:
        f.write(json.dumps(event) + "\\n")

def compile(self, **kwargs):
    record("compile", self.sketch_dir.name, self.profile)
    if os.environ.get("FAIL_PROFILE") == self.profile:
        raise RuntimeError("injected build failure")
    self.build_path.mkdir(parents=True, exist_ok=True)

def upload(self, **kwargs):
    record("upload", self.sketch_dir.name, self.profile, self.port)

def make_peer(request, target):
    record("peer_open", target.name, target.app.profile, target.runtime_port)
    def close():
        record("peer_close", target.name, target.app.profile)
        if os.environ.get("FAIL_CLEANUP") == target.app.profile:
            raise RuntimeError("injected cleanup failure")
    return SimpleNamespace(profile=target.app.profile, port=target.runtime_port), close

def pytest_configure(config):
    patch = pytest.MonkeyPatch()
    config._hardware_patch = patch
    patch.setattr(ArduinoCliBuildConfig, "compile", compile)
    patch.setattr(ArduinoCliUploadConfig, "upload", upload)
    patch.setattr(plugin, "_make_peer_dut", make_peer)
    patch.setattr(plugin, "_platform_has_own_monitor", lambda *a: False)

def pytest_unconfigure(config):
    config._hardware_patch.undo()

@pytest.fixture
def dut(request, arduino_cli_app):
    record("primary_open", arduino_cli_app.profile, request.config.option.port)
    yield SimpleNamespace(profile=arduino_cli_app.profile, port=request.config.option.port)
    record("primary_close", arduino_cli_app.profile)
'''


def sketch(directory, profiles, *, default="esp32"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{directory.name}.ino").write_text("void setup() {}\nvoid loop() {}\n")
    data = {"profiles": {name: ({"port": port} if port else {}) for name, port in profiles.items()}}
    if default is not None:
        data["default_profile"] = default
    (directory / "sketch.yaml").write_text(yaml.safe_dump(data))


def project(pytester, body, *, peer=True, peer_s3="/peer-s3"):
    pytester.makeconftest(HARDWARE)
    directory = pytester.path / "link"
    sketch(directory, {"esp32": "/primary-esp32", "esp32s3": "/primary-s3"})
    if peer:
        sketch(directory / "peer_echo", {"esp32": "/peer-esp32", "esp32s3": peer_s3})
    (directory / "test_link.py").write_text(textwrap.dedent(body))
    return directory


def run(pytester, *args):
    return pytester.runpytest(*args, "-p", "no:embedded-arduino-cli", "-p", "pytest_embedded_arduino_cli.plugin",
                             "--device-lock-dir", str(pytester.path / "locks"), "-q")


def events(pytester):
    path = pytester.path / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_primary_matrix_rebuilds_and_keeps_units_once(pytester):
    project(pytester, '''
        import pytest
        @pytest.mark.parametrize("value", [1, 2])
        def test_values(dut, value):
            assert dut.port == {"esp32": "/primary-esp32", "esp32s3": "/primary-s3"}[dut.profile]
    ''', peer=False)
    pytester.makepyfile(test_unit="def test_unit(): pass")
    result = run(pytester, "--profiles=all")
    result.assert_outcomes(passed=5)
    assert [e for e in events(pytester) if e[0] == "compile"] == [
        ["compile", "link", "esp32"], ["compile", "link", "esp32s3"]]


def test_peer_matrix_separates_lifecycle_reports_and_state(pytester):
    project(pytester, '''
        def test_link(dut, peers, arduino_test):
            assert peers["echo"].port == {"esp32": "/peer-esp32", "esp32s3": "/peer-s3"}[peers["echo"].profile]
            arduino_test._save_text_artifact("same", "result.txt", dut.profile + "/" + peers["echo"].profile)
    ''')
    result = run(pytester, "--profiles=all", "--peer-profiles=all", "--save-state", "--junitxml=results.xml")
    result.assert_outcomes(passed=4)
    log = events(pytester)
    assert len([e for e in log if e[0] == "compile"]) == 8
    assert len([e for e in log if e[0] == "peer_close"]) == 4
    for i, event in enumerate(log):
        if event[0] == "compile" and i > 0 and event[1] == "link":
            assert log[i - 1][0] in ("peer_close", "primary_close")
    state = json.loads((pytester.path / ".pytest-results/state.json").read_text())
    assert {name: len(data["tests"]) for name, data in state["profiles"].items()} == {"esp32": 2, "esp32s3": 2}
    artifacts = list((pytester.path / "ardutest").rglob("result.txt"))
    assert len(artifacts) == 4
    assert len({p.read_text() for p in artifacts}) == 4
    cases = ET.parse(pytester.path / "results.xml").findall(".//testcase")
    assert len({case.attrib["name"] for case in cases}) == 4
    assert all(case.find("properties/property[@name='arduino.peer.echo']") is not None for case in cases)


def test_missing_peer_skips_before_any_build(pytester):
    project(pytester, "def test_link(dut, peers): pass", peer_s3=None)
    result = run(pytester, "--profiles=all", "--peer-profiles=all", "-rs")
    result.assert_outcomes(passed=2, skipped=2)
    assert len([e for e in events(pytester) if e[0] == "compile"]) == 4
    assert not any(e[:3] == ["compile", "peer_echo", "esp32s3"] for e in events(pytester))


def test_marker_skips_before_build_and_collect_only_is_inert(pytester):
    project(pytester, '''
        import pytest
        def cross(item, combination):
            assert item.originalname == "test_link"
            return combination.primary != combination.peers["echo"]
        pytestmark = pytest.mark.arduino_skip_if(cross, reason="same profiles only")
        def test_link(dut, peers): pass
    ''')
    artifact = pytester.path / "ardutest/keep.txt"
    artifact.parent.mkdir()
    artifact.write_text("keep")
    args = ("--profiles=all", "--peer-profiles=all")
    result = run(pytester, *args, "--collect-only", "--clean")
    assert result.ret == 0
    assert "same profiles only" in result.stdout.str()
    assert artifact.read_text() == "keep"
    assert events(pytester) == []
    result = run(pytester, *args, "-rs")
    result.assert_outcomes(passed=2, skipped=2)
    assert len([e for e in events(pytester) if e[0] == "compile"]) == 4


def test_scoped_hooks_and_markers_accumulate_for_plain_tests(pytester):
    pytester.makeconftest('''
        def pytest_arduino_cli_skip_reason(item, combination):
            assert combination is None
            if item.originalname == "test_parent":
                return "parent restriction"
    ''')
    restricted = pytester.path / "restricted"
    restricted.mkdir()
    (restricted / "conftest.py").write_text('''
def pytest_arduino_cli_skip_reason(item, combination):
    if item.originalname == "test_child":
        return "child restriction"
''')
    (restricted / "test_inside.py").write_text('''
import pytest
pytestmark = pytest.mark.arduino_skip_if(lambda item, combination: False, reason="does not undo parent")
def test_parent(): assert False
def test_child(): assert False
def test_ok(): pass
''')
    pytester.makepyfile(test_sibling="def test_child(): pass")
    result = run(pytester, "-rs", "--strict-markers")
    result.assert_outcomes(passed=2, skipped=2)
    assert "child restriction" in result.stdout.str()
    assert "parent restriction" in result.stdout.str()


@pytest.mark.parametrize("expression", ["'yes'", "1 / 0", "pytest.skip('wrong API')"])
def test_bad_predicate_is_error_even_when_another_rule_skips(pytester, expression):
    project(pytester, f'''
        import pytest
        def broken(item, combination):
            return {expression}
        pytestmark = [
            pytest.mark.arduino_skip_if(lambda item, combination: True, reason="excluded"),
            pytest.mark.arduino_skip_if(broken, reason="broken"),
        ]
        def test_link(dut): pass
    ''', peer=False)
    result = run(pytester, "--profiles=all")
    assert result.ret != 0
    assert "arduino_skip_if" in result.stderr.str()
    assert events(pytester) == []


def test_build_failure_does_not_contaminate_next_profile(pytester, monkeypatch):
    monkeypatch.setenv("FAIL_PROFILE", "esp32")
    project(pytester, '''
        def test_one(dut): assert dut.profile == "esp32s3"
        def test_two(dut): assert dut.profile == "esp32s3"
    ''', peer=False)
    result = run(pytester, "--profiles=all", "--save-state")
    result.assert_outcomes(passed=2, errors=2)
    state = json.loads((pytester.path / ".pytest-results/state.json").read_text())
    assert set(state["profiles"]) == {"esp32s3"}


def test_exact_selection_and_last_failed(pytester):
    project(pytester, '''
        from pathlib import Path
        def test_link(dut, peers):
            if not Path("fixed").exists():
                assert (dut.profile, peers["echo"].profile) != ("esp32s3", "esp32")
    ''')
    args = ("--profiles=all", "--peer-profiles=all")
    run(pytester, *args).assert_outcomes(passed=3, failed=1)
    (pytester.path / "fixed").touch()
    run(pytester, *args, "--lf").assert_outcomes(passed=1)
    run(pytester, "link/test_link.py::test_link[primary=esp32,echo=esp32s3]", *args).assert_outcomes(passed=1)


def test_build_only_does_not_require_ports_or_distinct_devices(pytester):
    directory = project(pytester, "def test_link(dut, peers): assert False", peer_s3=None)
    sketch(directory, {"esp32": None, "esp32s3": None})
    result = run(pytester, "--profiles=all", "--peer-profiles=all", "--run-mode=build")
    result.assert_outcomes(skipped=4)
    assert len([e for e in events(pytester) if e[0] == "compile"]) == 8
    assert not any(e[0] == "upload" for e in events(pytester))


def test_peer_free_tests_are_not_multiplied_by_peers(pytester):
    project(pytester, '''
        import pytest
        @pytest.fixture
        def link(peers): return peers
        def test_without(dut): pass
        def test_with(dut, link): pass
    ''')
    result = run(pytester, "--profiles=all", "--peer-profiles=all")
    result.assert_outcomes(passed=6)
    assert len([e for e in events(pytester) if e[0] == "peer_open"]) == 4


@pytest.mark.parametrize("args", [
    ["--profiles=typo"], ["--profiles=esp32,esp32"], ["--profiles=all,esp32"],
    ["--profiles=all", "--profile=esp32"], ["--peer-profiles=missing:all"],
    ["--peer-profiles=all", "--peer-profile=echo:esp32"],
    ["--profiles=all", "--port=/shared"],
    ["--peer-profiles=all", "--peer-port=echo:/shared"],
])
def test_invalid_selection_fails_without_build(pytester, args):
    project(pytester, "def test_link(dut, peers): pass")
    result = run(pytester, *args)
    assert result.ret != 0
    assert events(pytester) == []


def test_physical_alias_collision_is_skipped_even_with_lock_off(pytester):
    directory = project(pytester, "def test_link(dut, peers): pass")
    device = pytester.path / "device"
    device.touch()
    alias = pytester.path / "alias"
    alias.symlink_to(device)
    sketch(directory, {"esp32": str(device)})
    sketch(directory / "peer_echo", {"esp32": str(alias)})
    result = run(pytester, "--profiles=all", "--peer-profiles=all", "--device-lock=off", "-rs")
    result.assert_outcomes(skipped=1)
    assert "duplicate device" in result.stdout.str()
    assert events(pytester) == []


def test_cleanup_failure_releases_other_peers_and_stops_reuse(pytester, monkeypatch):
    monkeypatch.setenv("FAIL_CLEANUP", "esp32")
    directory = project(pytester, "def test_link(dut, peers): pass")
    sketch(directory / "peer_other", {"esp32": "/other-esp32", "esp32s3": "/other-s3"})
    result = run(pytester, "--profiles=all", "--peer-profiles=all", "--save-state", "--root-logdir=logs")
    assert result.ret != 0
    result.assert_outcomes(passed=1, errors=1)
    assert len([e for e in events(pytester) if e[0] == "peer_close"]) == 2
    assert len([e for e in events(pytester) if e[0] == "upload"]) == 3
    state = json.loads((pytester.path / ".pytest-results/state.json").read_text())
    entry, = state["profiles"]["esp32"]["tests"].values()
    assert entry["last_result"] == "error"
    assert "last_success_at" not in entry
    summary, = (pytester.path / "logs").rglob("summary.json")
    payload = json.loads(summary.read_text())
    assert len(payload["planned"]) == 8
    assert len(payload["unfinished"]) == 7


def test_maxfail_preserves_unfinished_and_error_profile(pytester, monkeypatch):
    monkeypatch.setenv("FAIL_PROFILE", "esp32")
    project(pytester, "def test_link(dut): pass", peer=False)
    result = run(pytester, "--profiles=all", "--maxfail=1", "-rs", "--junitxml=result.xml")
    result.assert_outcomes(errors=1)
    assert "1 unfinished" in result.stdout.str()
    cases = ET.parse(pytester.path / "result.xml").findall(".//testcase")
    assert len(cases) == 1
    assert "primary=esp32]" in cases[0].attrib["name"]


def test_all_skipped_and_pure_units_do_not_update_state(pytester):
    directory = project(pytester, "def test_link(dut): pass", peer=False)
    sketch(directory, {"esp32": None, "esp32s3": None})
    pytester.makepyfile(test_unit="def test_unit(): pass")
    result = run(pytester, "--profiles=all", "--save-state")
    result.assert_outcomes(passed=1, skipped=2)
    state = json.loads((pytester.path / ".pytest-results/state.json").read_text())
    assert state["profiles"] == {}
    assert events(pytester) == []


def test_unsupported_sketch_keeps_skip_items(pytester):
    directory = project(pytester, "def test_link(dut): pass", peer=False)
    sketch(directory, {"esp32": "/primary-esp32"})
    another = pytester.path / "another"
    sketch(another, {"esp32s3": "/primary-s3"}, default="esp32s3")
    (another / "test_other.py").write_text("def test_other(dut): pass")
    result = run(pytester, "--profiles=esp32,esp32s3", "--junitxml=result.xml")
    result.assert_outcomes(passed=2, skipped=2)
    cases = ET.parse(pytester.path / "result.xml").findall(".//testcase")
    skipped = [case for case in cases if case.find("skipped") is not None]
    assert len(skipped) == 2
    for case in skipped:
        profile = case.find("properties/property[@name='arduino.primary']").attrib["value"]
        assert f"primary={profile}" in case.attrib["name"]


def test_default_only_and_explicit_peer_subset(pytester):
    project(pytester, "def test_link(dut, peers): pass")
    run(pytester).assert_outcomes(passed=1)
    run(pytester, "--profiles=all", "--peer-profiles=echo:esp32").assert_outcomes(passed=2)
    run(pytester, "--peer-profiles=all").assert_outcomes(passed=2)


def test_common_environment_does_not_hide_missing_matrix_ports(pytester, monkeypatch):
    directory = project(pytester, "def test_link(dut, peers): pass", peer_s3=None)
    sketch(directory, {"esp32": None, "esp32s3": None})
    monkeypatch.setenv("TEST_SERIAL_PORT", "/wrong-board")
    monkeypatch.setenv("TEST_SERIAL_PORT_PEER_ECHO", "/wrong-peer")
    monkeypatch.setenv("TEST_SERIAL_PORT_ESP32", "/primary-esp32")
    result = run(pytester, "--profiles=all", "--peer-profiles=all")
    result.assert_outcomes(passed=1, skipped=3)
    assert [e for e in events(pytester) if e[0] == "upload"] == [
        ["upload", "link", "esp32", "/primary-esp32"],
        ["upload", "peer_echo", "esp32", "/peer-esp32"],
    ]


def test_rules_apply_to_legacy_before_build(pytester):
    project(pytester, '''
        import pytest
        def excluded(item, combination):
            assert combination.primary == "esp32"
            return True
        @pytest.mark.arduino_skip_if(excluded, reason="not applicable")
        def test_link(dut, peers): pass
    ''')
    run(pytester).assert_outcomes(skipped=1)
    assert events(pytester) == []


def test_combination_is_immutable_and_all_markers_are_checked(pytester):
    project(pytester, '''
        import pytest
        def mutate(item, combination):
            combination.peers["echo"] = "esp32"
            return False
        pytestmark = pytest.mark.arduino_skip_if(lambda item, combination: True, reason="module")
        @pytest.mark.arduino_skip_if(mutate, reason="bad")
        def test_link(dut, peers): pass
    ''')
    result = run(pytester, "--profiles=all", "--peer-profiles=all")
    assert result.ret != 0
    assert "TypeError" in result.stderr.str()
    assert events(pytester) == []


@pytest.mark.parametrize("body", ["return False", "return ''", "raise ValueError('broken hook')"])
def test_hook_errors_are_not_hidden_as_skips(pytester, body):
    pytester.makeconftest(f"def pytest_arduino_cli_skip_reason(item, combination):\n    {body}\n")
    pytester.makepyfile(test_plain="def test_plain(): pass")
    result = run(pytester)
    assert result.ret != 0
    assert "pytest_arduino_cli_skip_reason" in result.stderr.str()


def test_missing_peer_default_is_skip_not_implicit_all(pytester):
    directory = project(pytester, "def test_link(dut, peers): pass")
    sketch(directory / "peer_echo", {"esp32": "/peer-esp32"}, default=None)
    result = run(pytester, "--profiles=all", "-rs")
    result.assert_outcomes(skipped=2)
    assert "profile is not resolved" in result.stdout.str()
    assert events(pytester) == []


@pytest.mark.parametrize("language", ["ja", "en"])
def test_published_guide_marker_and_hook_examples(pytester, language):
    filename = "TESTING_ADVANCED.ja.md" if language == "ja" else "TESTING_ADVANCED.md"
    guide = (Path(__file__).parents[1] / filename).read_text()
    snippets = re.findall(r"```python\n(.*?)```", guide, re.S)
    marker_example = next(code for code in snippets if code.startswith("# test_uart.py"))
    directory = project(pytester, marker_example)
    args = ("--profiles=all", "--peer-profiles=all", "--run-mode=build")
    result = run(pytester, *args)
    result.assert_outcomes(skipped=4)
    assert len([e for e in events(pytester) if e[0] == "compile"]) == 4
    # Exercise the exact documented hook independently of the marker.
    hook_example = next(code for code in snippets if code.startswith("# tests/wired/conftest.py"))
    (directory / "conftest.py").write_text(hook_example)
    (directory / "test_link.py").write_text("def test_link(dut, peers): pass")
    (pytester.path / "events.jsonl").unlink()
    run(pytester, *args).assert_outcomes(skipped=4)
    assert len([e for e in events(pytester) if e[0] == "compile"]) == 4


def test_class_function_and_parameter_rules_combine(pytester):
    project(pytester, '''
        import pytest
        @pytest.mark.arduino_skip_if(lambda item, combination: combination.primary == "esp32s3", reason="class")
        class TestLink:
            @pytest.mark.arduino_skip_if(lambda item, combination: False, reason="function does not undo class")
            @pytest.mark.parametrize("value", [
                1,
                pytest.param(2, marks=pytest.mark.arduino_skip_if(lambda item, combination: True, reason="parameter")),
            ])
            def test_link(self, dut, value):
                assert dut.profile == "esp32" and value == 1
    ''', peer=False)
    run(pytester, "--profiles=all", "-rs").assert_outcomes(passed=1, skipped=3)
    assert len([e for e in events(pytester) if e[0] == "compile"]) == 1


def test_all_device_locks_held_before_first_upload_and_released(pytester):
    project(pytester, '''
        from pathlib import Path
        from pytest_embedded_arduino_cli.device_lock import DeviceLock, DeviceLockInfo, DeviceLockError
        import pytest
        def test_link(dut, peers): pass
    ''')
    (pytester.path / "conftest.py").write_text(HARDWARE + '''
from pytest_embedded_arduino_cli.device_lock import DeviceLock, DeviceLockInfo, DeviceLockError
original_upload = upload
def upload(self, **kwargs):
    if self.sketch_dir.name == "link":
        for port in ("/primary-esp32", "/peer-esp32"):
            lock = DeviceLock(DeviceLockInfo(key=port), lock_dir=ROOT / "locks", timeout=0.001)
            with pytest.raises(DeviceLockError):
                lock.acquire()
    return original_upload(self, **kwargs)
''')
    run(pytester, "--profiles=esp32", "--peer-profiles=echo:esp32").assert_outcomes(passed=1)
    from pytest_embedded_arduino_cli.device_lock import DeviceLock, DeviceLockInfo
    for port in ("/primary-esp32", "/peer-esp32"):
        lock = DeviceLock(DeviceLockInfo(key=port), lock_dir=pytester.path / "locks", timeout=0.001)
        lock.acquire()
        lock.release()


def test_host_placeholders_complete_per_configuration(pytester):
    directory = project(pytester, '''
        def test_link(dut, peers):
            expected = "socket://localhost:54001" if dut.profile == "esp32" else "socket://localhost:54002"
            assert dut.port == expected
            assert peers["echo"].port.startswith("socket://localhost:5401")
    ''')
    sketch(directory, {"esp32": "socket://localhost", "esp32s3": "socket://localhost"})
    sketch(directory / "peer_echo", {"esp32": "socket://localhost", "esp32s3": "socket://localhost"})
    (pytester.path / "conftest.py").write_text(HARDWARE + '''
original_configure = pytest_configure
def pytest_configure(config):
    original_configure(config)
    config._hardware_patch.setattr(plugin, "wait_for_socket_url", lambda *args: None)
original_upload = upload
def upload(self, **kwargs):
    assert self.port is None
    base = 54010 if self.sketch_dir.name.startswith("peer_") else 54000
    port = base + (1 if self.profile == "esp32" else 2)
    (self.build_path / "app.host-arduino.json").write_text(json.dumps({"port": port}))
    return original_upload(self, **kwargs)
''')
    run(pytester, "--profiles=all", "--peer-profiles=all").assert_outcomes(passed=4)


def test_same_function_names_in_different_modules_have_separate_logs(pytester):
    directory = project(pytester, '''
        from pathlib import Path
        def test_link(dut, test_case_tempdir):
            path = Path(test_case_tempdir)
            path.mkdir(parents=True, exist_ok=True)
            (path / "dut.log").write_text(dut.profile)
    ''', peer=False)
    another = pytester.path / "another"
    sketch(another, {"esp32": "/another-esp32", "esp32s3": "/another-s3"})
    (another / "test_other.py").write_text((directory / "test_link.py").read_text())
    run(pytester, "--profiles=all", "--root-logdir=logs").assert_outcomes(passed=4)
    summary, = (pytester.path / "logs").rglob("summary.json")
    payload = json.loads(summary.read_text())
    assert len({entry["dir"] for entry in payload["tests"]}) == 4
    assert len(list((pytester.path / "logs").rglob("dut.log"))) == 4
    assert {entry["profile"] for entry in payload["tests"]} == {"esp32", "esp32s3"}


def test_entrypoint_autoload_also_uses_configuration_log_directories(pytester, monkeypatch):
    monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", raising=False)
    project(pytester, '''
        from pathlib import Path
        def test_link(dut, test_case_tempdir, build_dir, arduino_cli_app):
            assert Path(build_dir) == arduino_cli_app.build_path
            assert Path(test_case_tempdir).name.startswith("test_link[")
            assert not Path(test_case_tempdir).name.endswith("]")  # full-identity hash suffix
    ''', peer=False)
    result = pytester.runpytest_subprocess("--profiles=all", "--device-lock=off", "-q")
    result.assert_outcomes(passed=2)


def test_parametrized_port_cannot_bypass_profile_assignment(pytester):
    project(pytester, '''
        import pytest
        @pytest.mark.parametrize("port", ["/wrong-device"], indirect=True)
        def test_link(dut): pass
    ''', peer=False)
    result = run(pytester, "--profiles=all")
    assert result.ret != 0
    assert "combination mode owns port" in result.stderr.str()
    assert events(pytester) == []


COMBOS_INI = """
[pytest]
arduino_combos =
    pair32: primary=esp32,echo=esp32
    pairs3: primary=esp32s3,echo=esp32s3
"""


def test_combo_runs_only_the_listed_pairs(pytester):
    project(pytester, "def test_link(dut, peers): assert peers['echo'].profile == dut.profile")
    result = run(pytester, "--combo", "primary=esp32,echo=esp32", "--combo", "primary=esp32s3,echo=esp32s3", "--co")
    result.stdout.fnmatch_lines(["*test_link[[]primary=esp32,echo=esp32[]]", "*test_link[[]primary=esp32s3,echo=esp32s3[]]"])
    run(pytester, "--combo", "primary=esp32,echo=esp32", "--combo", "primary=esp32s3,echo=esp32s3").assert_outcomes(passed=2)
    assert [e[1:] for e in events(pytester) if e[0] == "peer_open"] == [
        ["echo", "esp32", "/peer-esp32"], ["echo", "esp32s3", "/peer-s3"]]


def test_combo_names_and_all_come_from_ini(pytester):
    project(pytester, "def test_link(dut, peers): assert peers['echo'].profile == dut.profile")
    pytester.makeini(COMBOS_INI)
    run(pytester, "--combo", "all").assert_outcomes(passed=2)
    run(pytester, "--combo", "pairs3").assert_outcomes(passed=1)
    run(pytester, "--combo", "pair32", "--combo", "primary=esp32s3,echo=esp32s3").assert_outcomes(passed=2)


def test_combo_is_read_from_pyproject(pytester):
    project(pytester, "def test_link(dut, peers): assert peers['echo'].profile == dut.profile")
    pytester.makepyprojecttoml("""
        [tool.pytest.ini_options]
        arduino_combos = ["s3: primary=esp32s3,echo=esp32s3"]
    """)
    run(pytester, "--combo", "s3").assert_outcomes(passed=1)


def test_combo_peer_free_tests_run_once_per_primary(pytester):
    project(pytester, '''
        def test_without(dut): pass
        def test_with(dut, peers): pass
    ''')
    result = run(pytester, "--combo", "primary=esp32,echo=esp32", "--combo", "primary=esp32,echo=esp32s3")
    result.assert_outcomes(passed=3)


def test_combo_unlisted_peer_keeps_its_default(pytester):
    project(pytester, "def test_link(dut, peers): assert peers['echo'].profile == 'esp32'")
    run(pytester, "--combo", "primary=esp32s3").assert_outcomes(passed=1)


def test_combo_skips_sketch_no_combo_fits_once(pytester):
    directory = project(pytester, "def test_link(dut, peers): pass")
    other = pytester.path / "other"
    sketch(other, {"uno": "/uno"}, default="uno")
    (other / "test_other.py").write_text("def test_other(dut): pass")
    pytester.makeini(COMBOS_INI)
    result = run(pytester, "--combo", "all", "-rs")
    result.assert_outcomes(passed=2, skipped=1)
    result.stdout.fnmatch_lines(["*no --combo applies to this sketch (primary profiles: uno)*"])
    assert all(e[1] != "other" for e in events(pytester) if e[0] == "compile")
    assert directory.exists()


@pytest.mark.parametrize("args", [
    ["--combo", "primary=esp32", "--profiles=all"],
    ["--combo", "primary=esp32", "--profile=esp32"],
    ["--combo", "primary=esp32", "--peer-profile=echo:esp32"],
    ["--combo", "primary=esp32", "--peer-profiles=all"],
    ["--combo", "missing"],
    ["--combo", "all"],
    ["--combo", "all", "--combo", "primary=esp32"],
    ["--combo", "echo=esp32"],
    ["--combo", "primary=esp32,primary=esp32s3"],
    ["--combo", "primary=esp32", "--combo", "primary=esp32"],
    ["--combo", "primary=typo"],
    ["--combo", "primary=esp32,ehco=esp32"],
    ["--combo", "primary=esp32,echo=typo"],
    ["--combo", "primary=esp32", "--combo", "primary=esp32s3", "--port=/shared"],
])
def test_invalid_combo_fails_without_build(pytester, args):
    project(pytester, "def test_link(dut, peers): pass")
    result = run(pytester, *args)
    assert result.ret != 0
    assert events(pytester) == []


def test_combo_that_fits_no_sketch_is_an_error(pytester):
    project(pytester, "def test_link(dut, peers): pass")
    other = pytester.path / "other"
    sketch(other, {"uno": "/uno"}, default="uno")
    sketch(other / "peer_echo", {"uno": "/peer-uno"}, default="uno")
    (other / "test_other.py").write_text("def test_other(dut, peers): pass")
    result = run(pytester, "--combo", "primary=esp32,echo=uno")
    assert result.ret != 0
    assert "no collected sketch defines all of its profiles" in result.stderr.str()


def test_single_combo_keeps_common_port(pytester):
    project(pytester, "def test_link(dut): assert dut.port == '/shared'", peer=False)
    run(pytester, "--combo", "primary=esp32s3", "--port=/shared").assert_outcomes(passed=1)


RESET_PROBE = '''
from pathlib import Path
def test_link(dut, peers):
    here = Path(__file__).parent
    assert not (here / "output").exists()
    assert not (here / "peer_echo" / "output").exists()
    assert (here / "keep" / "file").exists()
'''


def test_reset_dirs_are_removed_before_the_sketch_starts(pytester):
    directory = project(pytester, RESET_PROBE)
    pytester.makeini("[pytest]\narduino_reset_dirs = output\n")
    for path in (directory / "output", directory / "peer_echo" / "output", directory / "keep"):
        path.mkdir()
        (path / "file").write_text("stale")
    pytester.makeconftest(HARDWARE.replace(
        'record("primary_open"', 'assert not (ROOT / "link" / "output").exists()\n    record("primary_open"'))
    run(pytester).assert_outcomes(passed=1)
    assert (directory / "keep" / "file").exists()


def test_reset_dirs_off_by_default(pytester):
    directory = project(pytester, "def test_link(dut): pass", peer=False)
    (directory / "output").mkdir()
    run(pytester).assert_outcomes(passed=1)
    assert (directory / "output").exists()


@pytest.mark.parametrize("value", ["../output", "/tmp/output", ".", "a/../../b"])
def test_reset_dirs_rejects_paths_outside_the_test_directory(pytester, value):
    project(pytester, "def test_link(dut): pass", peer=False)
    pytester.makeini(f"[pytest]\narduino_reset_dirs = {value}\n")
    result = run(pytester)
    assert result.ret != 0
    assert "arduino_reset_dirs" in result.stderr.str()


def test_reset_dirs_refuses_symlinks(pytester, tmp_path_factory):
    directory = project(pytester, "def test_link(dut): pass", peer=False)
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    (elsewhere / "file").write_text("keep")
    (directory / "output").symlink_to(elsewhere, target_is_directory=True)
    pytester.makeini("[pytest]\narduino_reset_dirs = output\n")
    result = run(pytester)
    result.assert_outcomes(errors=1)
    assert (elsewhere / "file").exists()
