from __future__ import annotations

import re

import pytest

from pytest_embedded_arduino_cli.ardutest import (
    ARDUTEST_PROTOCOL_LINE_RE,
    ArduTestSession,
    parse_ardutest_line,
)


class FakeMatch:
    def __init__(self, *values: bytes) -> None:
        self.values = values

    def group(self, index: int) -> bytes:
        return self.values[index - 1]


class ProtocolFakeDut:
    def __init__(self, lines: list[str]) -> None:
        self.buffer = bytearray()
        for line in lines:
            if "\n" in line:
                self.buffer.extend(line.encode())
            else:
                self.buffer.extend(f"{line}\n".encode())
        self.writes: list[str] = []

    def write(self, value: str) -> None:
        self.writes.append(value)

    def expect(self, pattern: re.Pattern[bytes], timeout: float):
        assert timeout == 30.0
        if not self.buffer:
            raise AssertionError("unexpected expect call")
        match = pattern.search(bytes(self.buffer))
        assert match is not None
        del self.buffer[: match.end()]
        return FakeMatch(match.group(1))


def test_parse_ardutest_line_splits_kind_and_fields() -> None:
    parsed = parse_ardutest_line("RESULT test_example passed")

    assert parsed.kind == "RESULT"
    assert parsed.fields == "test_example passed"


def test_ardutest_session_runs_protocol_by_name() -> None:
    dut = ProtocolFakeDut(
        [
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_true_passes",
            "AT < TEST test_metric_and_artifact",
            "AT < REQUIRE test_metric_and_artifact measurement.current",
            "AT < REQUIRE_CONFIG test_metric_and_artifact sample_rate",
            "AT < END_LIST",
            "AT < RUNNING test_metric_and_artifact",
            "AT < METRIC test_metric_and_artifact example_value 42",
            "AT < LOG test_metric_and_artifact 11\nhello world",
            "AT < ARTIFACT_TEXT test_metric_and_artifact note.txt text/plain 19\nhello from ArduTest",
            "AT < RESULT test_metric_and_artifact passed",
        ]
    )

    results = ArduTestSession(
        dut,
        environ={
            "ARDUINO_TEST_CAP_MEASUREMENT_CURRENT": "true",
            "ARDUINO_TEST_CONFIG_SAMPLE_RATE": "1000",
        },
    ).run("test_metric_and_artifact")

    assert dut.writes == [
        "AT > HELLO 1\n",
        "AT > LIST\n",
        "AT > CLEAR_CONFIG\n",
        "AT > SET_CONFIG sample_rate 4\n1000",
        "AT > RUN test_metric_and_artifact\n",
    ]
    assert [result.name for result in results] == ["test_metric_and_artifact"]
    assert results[0].metrics == {"example_value": [42]}
    assert results[0].logs == ["hello world"]
    assert results[0].artifacts == {"note.txt": "hello from ArduTest"}


def test_ardutest_session_saves_text_artifacts(tmp_path) -> None:
    dut = ProtocolFakeDut(
        [
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_metric_and_artifact",
            "AT < END_LIST",
            "AT < RUNNING test_metric_and_artifact",
            "AT < ARTIFACT_TEXT test_metric_and_artifact notes/note.txt text/plain 19\nhello from ArduTest",
            "AT < RESULT test_metric_and_artifact passed",
        ]
    )

    ArduTestSession(dut, artifact_dir=tmp_path / "ardutest").run()

    assert (tmp_path / "ardutest" / "test_metric_and_artifact" / "notes" / "note.txt").read_text(
        encoding="utf-8"
    ) == "hello from ArduTest"


def test_ardutest_session_does_not_create_empty_artifact_dir(tmp_path) -> None:
    dut = ProtocolFakeDut(
        [
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_true_passes",
            "AT < END_LIST",
            "AT < RUNNING test_true_passes",
            "AT < RESULT test_true_passes passed",
        ]
    )

    ArduTestSession(dut, artifact_dir=tmp_path / "ardutest").run()

    assert not (tmp_path / "ardutest").exists()


def test_ardutest_session_rejects_unsafe_artifact_filename(tmp_path) -> None:
    dut = ProtocolFakeDut(
        [
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_metric_and_artifact",
            "AT < END_LIST",
            "AT < RUNNING test_metric_and_artifact",
            "AT < ARTIFACT_TEXT test_metric_and_artifact ../note.txt text/plain 19\nhello from ArduTest",
        ]
    )

    with pytest.raises(RuntimeError, match="invalid ArduTest artifact filename"):
        ArduTestSession(dut, artifact_dir=tmp_path / "ardutest").run()


def test_ardutest_session_skips_missing_capability_without_running() -> None:
    dut = ProtocolFakeDut(
        [
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_metric_and_artifact",
            "AT < REQUIRE test_metric_and_artifact measurement.current",
            "AT < END_LIST",
        ]
    )

    results = ArduTestSession(dut, environ={}).run()

    assert dut.writes == [
        "AT > HELLO 1\n",
        "AT > LIST\n",
    ]
    assert results[0].status == "skipped"
    assert results[0].skip_reason == "missing capability: measurement.current"


def test_ardutest_session_skips_missing_config_without_running() -> None:
    dut = ProtocolFakeDut(
        [
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_metric_and_artifact",
            "AT < REQUIRE_CONFIG test_metric_and_artifact sample_rate",
            "AT < END_LIST",
        ]
    )

    results = ArduTestSession(dut, environ={}).run()

    assert dut.writes == [
        "AT > HELLO 1\n",
        "AT > LIST\n",
    ]
    assert results[0].status == "skipped"
    assert results[0].skip_reason == "missing config: sample_rate"


def test_ardutest_session_lists_metadata() -> None:
    dut = ProtocolFakeDut(
        [
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_true_passes",
            "AT < TEST test_metric_and_artifact",
            "AT < REQUIRE test_metric_and_artifact measurement.current",
            "AT < REQUIRE_CONFIG test_metric_and_artifact sample_rate",
            "AT < END_LIST",
        ]
    )

    tests = ArduTestSession(dut).list_tests()

    assert tests[0].name == "test_true_passes"
    assert tests[1].name == "test_metric_and_artifact"
    assert tests[1].requirements == ("measurement.current",)
    assert tests[1].required_configs == ("sample_rate",)


def test_ardutest_session_reuses_listed_metadata_for_run() -> None:
    dut = ProtocolFakeDut(
        [
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_metric_and_artifact",
            "AT < REQUIRE_CONFIG test_metric_and_artifact sample_rate",
            "AT < END_LIST",
            "AT < RUNNING test_metric_and_artifact",
            "AT < METRIC test_metric_and_artifact sample_rate 1000",
            "AT < RESULT test_metric_and_artifact passed",
        ]
    )
    session = ArduTestSession(dut, environ={"ARDUINO_TEST_CONFIG_SAMPLE_RATE": "1000"})

    assert [test.name for test in session.list_tests()] == ["test_metric_and_artifact"]
    results = session.run("test_metric_and_artifact")

    assert dut.writes == [
        "AT > HELLO 1\n",
        "AT > LIST\n",
        "AT > CLEAR_CONFIG\n",
        "AT > SET_CONFIG sample_rate 4\n1000",
        "AT > RUN test_metric_and_artifact\n",
    ]
    assert results[0].metrics == {"sample_rate": [1000]}
    assert session.metrics == {"test_metric_and_artifact": {"sample_rate": [1000]}}


def test_ardutest_session_resends_hello_after_ready() -> None:
    dut = ProtocolFakeDut(
        [
            "AT < READY",
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_true_passes",
            "AT < END_LIST",
            "AT < RUNNING test_true_passes",
            "AT < RESULT test_true_passes passed",
        ]
    )

    results = ArduTestSession(dut).run()

    assert dut.writes == [
        "AT > HELLO 1\n",
        "AT > HELLO 1\n",
        "AT > HELLO 1\n",
        "AT > LIST\n",
        "AT > RUN test_true_passes\n",
    ]
    assert [result.name for result in results] == ["test_true_passes"]


def test_ardutest_session_ignores_duplicate_hello_before_list_items() -> None:
    dut = ProtocolFakeDut(
        [
            "AT < READY",
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_true_passes",
            "AT < END_LIST",
            "AT < RUNNING test_true_passes",
            "AT < RESULT test_true_passes passed",
        ]
    )

    results = ArduTestSession(dut).run()

    assert [result.name for result in results] == ["test_true_passes"]


def test_ardutest_session_errors_on_unknown_selected_name() -> None:
    dut = ProtocolFakeDut(
        [
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_true_passes",
            "AT < END_LIST",
        ]
    )

    with pytest.raises(RuntimeError, match="unknown ArduTest test: missing"):
        ArduTestSession(dut).run("missing")


def test_ardutest_session_fails_pytest_on_failed_result() -> None:
    dut = ProtocolFakeDut(
        [
            "AT < HELLO 1 ArduTest 0.1.0",
            "AT < TEST test_fails",
            "AT < END_LIST",
            "AT < RUNNING test_fails",
            "AT < FAIL test_fails sketch.ino 10 5\nfalse",
            "AT < RESULT test_fails failed",
        ]
    )

    with pytest.raises(AssertionError, match="test_fails: failed"):
        ArduTestSession(dut).run()
