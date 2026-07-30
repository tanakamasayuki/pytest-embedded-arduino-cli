from pathlib import Path
import json

import pytest

from pytest_embedded_arduino_cli.log_summary import (
    _looks_like_root_marker,
    _root_marker_name,
    _safe_subdir,
    _truncate_tail,
    LogSummaryCollector,
)


class DummyReport:
    def __init__(self, nodeid: str, when: str, outcome: str, duration: float = 0.5, longrepr=None) -> None:
        self.nodeid = nodeid
        self.when = when
        self.outcome = outcome
        self.duration = duration
        self.longrepr = longrepr


class DummyConfig:
    def __init__(self, rootpath: Path) -> None:
        self.rootpath = rootpath
        self.invocation_params = type("Params", (), {"args": ("-k", "spi test")})()
        self._options = {"profile": "esp32s3", "run_mode": "all"}

    def getoption(self, name, default=None):
        return self._options.get(name, default)


class DummySession:
    def __init__(self, rootpath: Path) -> None:
        self.config = DummyConfig(rootpath)


def _write(tmp_path: Path, reports) -> Path:
    collector = LogSummaryCollector()
    for report in reports:
        collector.record(report, "esp32s3")
    session_tempdir = tmp_path / "2026-07-30_08-03-16-959795"
    session_tempdir.mkdir()
    collector.write(session_tempdir, DummySession(tmp_path), 1)
    return session_tempdir


def test_writes_marker_per_test_and_root_marker(tmp_path):
    log_dir = _write(
        tmp_path,
        [
            DummyReport("tests/test_a.py::test_pass", "setup", "passed", 1.0),
            DummyReport("tests/test_a.py::test_pass", "call", "passed", 2.0),
            DummyReport("tests/test_a.py::test_pass", "teardown", "passed", 0.25),
            DummyReport("tests/test_a.py::test_fail", "call", "failed", 3.5, longrepr="assert 1 == 2"),
            DummyReport("tests/test_a.py::test_skip", "setup", "skipped", 0.0, longrepr=("f.py", 3, "no board")),
            DummyReport("tests/test_a.py::test_error", "setup", "failed", 0.5, longrepr="upload failed"),
        ],
    )

    assert (log_dir / "FAILED-1_ERROR-1_PASSED-1_SKIPPED-1").exists() is False
    assert (log_dir / "ERROR-1_FAILED-1_PASSED-1_SKIPPED-1").exists()
    assert (log_dir / "test_pass" / "PASSED.txt").exists()
    assert (log_dir / "test_error" / "ERROR.txt").exists()
    assert (log_dir / "test_skip" / "SKIPPED.txt").exists()

    passed = (log_dir / "test_pass" / "PASSED.txt").read_text()
    assert "status: PASSED" in passed
    assert "tests/test_a.py::test_pass" in passed
    assert "duration: 3.25s" in passed
    assert "setup 1.00s, call 2.00s, teardown 0.25s" in passed
    assert "profile: esp32s3" in passed

    failed = (log_dir / "test_fail" / "FAILED.txt").read_text()
    assert "status: FAILED" in failed
    assert "assert 1 == 2" in failed

    assert "no board" in (log_dir / "test_skip" / "SKIPPED.txt").read_text()
    assert "upload failed" in (log_dir / "test_error" / "ERROR.txt").read_text()


def test_summary_files_describe_the_run(tmp_path):
    log_dir = _write(
        tmp_path,
        [
            DummyReport("tests/test_a.py::test_pass", "call", "passed", 2.0),
            DummyReport("tests/test_a.py::test_fail", "call", "failed", 1.0, longrepr="boom"),
        ],
    )

    summary = (log_dir / "SUMMARY.txt").read_text()
    assert "result: FAILED-1_PASSED-1" in summary
    assert "exit status: 1" in summary
    assert "profile: esp32s3" in summary
    assert "run-mode: all" in summary
    assert "pytest -k 'spi test'" in summary
    assert "total duration: 3.00s" in summary
    assert "FAILED       1.00s  tests/test_a.py::test_fail" in summary
    assert "tests/test_a.py::test_fail (call) -> test_fail/FAILED.txt" in summary
    assert "    boom" in summary

    payload = json.loads((log_dir / "summary.json").read_text())
    assert payload["result"] == "FAILED-1_PASSED-1"
    assert payload["counts"] == {"FAILED": 1, "PASSED": 1}
    assert payload["exit_status"] == 1
    assert payload["total_duration"] == 3.0
    assert [test["nodeid"] for test in payload["tests"]] == [
        "tests/test_a.py::test_fail",
        "tests/test_a.py::test_pass",
    ]
    failing = payload["tests"][0]
    assert failing["status"] == "FAILED"
    assert failing["dir"] == "test_fail"
    assert failing["message"] == "boom"
    assert failing["phases"] == {"call": {"outcome": "failed", "duration": 1.0}}


def test_marker_keeps_existing_logs_and_lists_them(tmp_path):
    session_tempdir = tmp_path / "run"
    test_dir = session_tempdir / "test_pass"
    test_dir.mkdir(parents=True)
    (test_dir / "dut.log").write_text("boot")
    (test_dir / "peer-device.log").write_text("boot")

    collector = LogSummaryCollector()
    collector.record(DummyReport("tests/test_a.py::test_pass", "call", "passed"), None)
    collector.write(session_tempdir, DummySession(tmp_path), 0)

    marker = (test_dir / "PASSED.txt").read_text()
    assert "logs: dut.log, peer-device.log" in marker
    assert (test_dir / "dut.log").read_text() == "boot"


def test_stale_markers_are_replaced(tmp_path):
    session_tempdir = tmp_path / "run"
    test_dir = session_tempdir / "test_pass"
    test_dir.mkdir(parents=True)
    (test_dir / "FAILED.txt").write_text("from a previous run")
    (session_tempdir / "FAILED-1").touch()

    collector = LogSummaryCollector()
    collector.record(DummyReport("tests/test_a.py::test_pass", "call", "passed"), None)
    collector.write(session_tempdir, DummySession(tmp_path), 0)

    assert not (test_dir / "FAILED.txt").exists()
    assert (test_dir / "PASSED.txt").exists()
    assert not (session_tempdir / "FAILED-1").exists()
    assert (session_tempdir / "PASSED-1").exists()


def test_tests_sharing_a_directory_name_report_the_worst_status(tmp_path):
    log_dir = _write(
        tmp_path,
        [
            DummyReport("tests/test_a.py::test_dup", "call", "passed", 1.0),
            DummyReport("tests/test_b.py::test_dup", "call", "failed", 2.0, longrepr="boom"),
        ],
    )

    assert not (log_dir / "test_dup" / "PASSED.txt").exists()
    marker = (log_dir / "test_dup" / "FAILED.txt").read_text()
    assert "status: FAILED" in marker
    assert "tests/test_a.py::test_dup" in marker
    assert "tests/test_b.py::test_dup" in marker
    assert "boom" in marker


def test_nothing_written_without_reports(tmp_path):
    session_tempdir = tmp_path / "run"
    session_tempdir.mkdir()
    LogSummaryCollector().write(session_tempdir, DummySession(tmp_path), 0)
    assert list(session_tempdir.iterdir()) == []


@pytest.mark.parametrize(
    "counts, expected",
    [
        ({}, "NO-TESTS"),
        ({"PASSED": 9}, "PASSED-9"),
        ({"PASSED": 7, "FAILED": 2, "SKIPPED": 1}, "FAILED-2_PASSED-7_SKIPPED-1"),
    ],
)
def test_root_marker_name(counts, expected):
    assert _root_marker_name(counts) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("FAILED-2_PASSED-7", True),
        ("NO-TESTS", True),
        ("SUMMARY.txt", False),
        ("summary.json", False),
        ("dut.log", False),
        ("PASSED-x", False),
    ],
)
def test_looks_like_root_marker(name, expected):
    assert _looks_like_root_marker(name) is expected


def test_safe_subdir_refuses_escaping_names(tmp_path):
    assert _safe_subdir(tmp_path, "test_ok") == tmp_path / "test_ok"
    assert _safe_subdir(tmp_path, "..") is None
    assert _safe_subdir(tmp_path, "../evil") is None
    assert _safe_subdir(tmp_path, "") is None


def _run_with_embedded_logdir(pytester, root_logdir: Path, *extra_args: str):
    pytester.makepyfile(
        test_sample="""
        def test_ok(session_tempdir):
            assert session_tempdir

        def test_ng(session_tempdir):
            assert 1 == 2, "board did not answer"
        """
    )
    result = pytester.runpytest("--root-logdir", str(root_logdir), *extra_args)
    result.assert_outcomes(passed=1, failed=1)
    session_dirs = sorted((root_logdir / "pytest-embedded").glob("*"))
    return [path for path in session_dirs if path.is_dir() and path.name != "pytest-embedded-cache"]


def test_end_to_end_writes_markers_into_the_embedded_log_dir(pytester, tmp_path):
    root_logdir = tmp_path / "logs"
    session_dirs = _run_with_embedded_logdir(pytester, root_logdir)

    assert len(session_dirs) == 1
    log_dir = session_dirs[0]
    assert (log_dir / "FAILED-1_PASSED-1").exists()
    assert (log_dir / "test_ok" / "PASSED.txt").exists()
    assert "board did not answer" in (log_dir / "test_ng" / "FAILED.txt").read_text()
    assert "result: FAILED-1_PASSED-1" in (log_dir / "SUMMARY.txt").read_text()
    assert json.loads((log_dir / "summary.json").read_text())["counts"] == {"FAILED": 1, "PASSED": 1}


def test_end_to_end_opt_out(pytester, tmp_path):
    root_logdir = tmp_path / "logs"
    session_dirs = _run_with_embedded_logdir(pytester, root_logdir, "--arduino-cli-no-log-summary")

    assert len(session_dirs) == 1
    log_dir = session_dirs[0]
    assert not (log_dir / "SUMMARY.txt").exists()
    assert not (log_dir / "summary.json").exists()
    assert not list(log_dir.glob("*PASSED*"))


def test_truncate_tail_keeps_the_end():
    text = "\n".join(f"line {index}" for index in range(20000))
    truncated = _truncate_tail(text)
    assert truncated.startswith("[... ")
    assert "characters dropped" in truncated
    assert truncated.endswith("line 19999")
    assert len(truncated) < len(text)
