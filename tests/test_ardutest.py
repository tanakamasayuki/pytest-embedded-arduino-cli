from __future__ import annotations

import re

import pytest

from pytest_embedded_arduino_cli.ardutest import (
    ARDUTEST_LINE_RE,
    ArduTestSession,
    parse_ardutest_line,
)


class FakeMatch:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def group(self, index: int) -> bytes:
        assert index == 1
        return self.value


class FakeDut:
    def __init__(self, lines: list[str]) -> None:
        self.lines = [f"{line}\n".encode() for line in lines]
        self.patterns: list[re.Pattern[bytes]] = []

    def expect(self, pattern: re.Pattern[bytes], timeout: float):
        assert pattern == ARDUTEST_LINE_RE
        assert timeout == 30.0
        self.patterns.append(pattern)
        if not self.lines:
            raise AssertionError("unexpected expect call")
        line = self.lines.pop(0)
        match = pattern.search(line)
        assert match is not None
        return FakeMatch(match.group(1))


def test_parse_ardutest_line_splits_kind_and_fields() -> None:
    parsed = parse_ardutest_line("RESULT test_example passed")

    assert parsed.kind == "RESULT"
    assert parsed.fields == "test_example passed"


def test_ardutest_session_collects_passing_results() -> None:
    dut = FakeDut(
        [
            "ARDUTEST BEGIN 0.1.0",
            "ARDUTEST TESTS 2",
            "ARDUTEST RUN test_true_passes",
            "ARDUTEST LOG test_true_passes running test_true_passes",
            "ARDUTEST RESULT test_true_passes passed",
            "ARDUTEST RUN test_metric_and_artifact",
            "ARDUTEST METRIC test_metric_and_artifact example_value 42",
            "ARDUTEST ARTIFACT_TEXT test_metric_and_artifact note.txt hello from ArduTest",
            "ARDUTEST RESULT test_metric_and_artifact passed",
        ]
    )

    results = ArduTestSession(dut).run()

    assert [result.name for result in results] == [
        "test_true_passes",
        "test_metric_and_artifact",
    ]
    assert [result.status for result in results] == ["passed", "passed"]
    assert results[1].events[0].kind == "METRIC"


def test_ardutest_session_fails_pytest_on_failed_result() -> None:
    dut = FakeDut(
        [
            "ARDUTEST BEGIN 0.1.0",
            "ARDUTEST TESTS 1",
            "ARDUTEST RUN test_fails",
            "ARDUTEST FAIL test_fails sketch.ino:10 false",
            "ARDUTEST RESULT test_fails failed",
        ]
    )

    with pytest.raises(AssertionError, match="test_fails: failed"):
        ArduTestSession(dut).run()
