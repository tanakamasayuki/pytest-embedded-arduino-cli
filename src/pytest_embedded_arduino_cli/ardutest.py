from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal


ArduTestStatus = Literal["passed", "failed", "error"]


class ArduTestError(RuntimeError):
    """Raised when ArduTest output cannot be collected correctly."""


@dataclass(frozen=True)
class ArduTestEvent:
    kind: str
    test_name: str | None
    message: str


@dataclass
class ArduTestResult:
    name: str
    status: ArduTestStatus
    events: list[ArduTestEvent] = field(default_factory=list)

    @property
    def logs(self) -> list[str]:
        return [event.message for event in self.events if event.kind == "LOG"]

    @property
    def metrics(self) -> dict[str, list[int | float | str]]:
        values: dict[str, list[int | float | str]] = {}
        for event in self.events:
            if event.kind != "METRIC":
                continue
            name, value = _split_name_value(event.message)
            values.setdefault(name, []).append(_parse_metric_value(value))
        return values

    @property
    def artifacts(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for event in self.events:
            if event.kind != "ARTIFACT_TEXT":
                continue
            name, value = _split_name_value(event.message)
            values[name] = value
        return values


@dataclass(frozen=True)
class ParsedArduTestLine:
    kind: str
    fields: str


ARDUTEST_LINE_RE = re.compile(rb"ARDUTEST ([^\r\n]+)\r?\n")


def parse_ardutest_line(line: str) -> ParsedArduTestLine:
    try:
        kind, fields = line.split(" ", 1)
    except ValueError:
        kind, fields = line, ""
    return ParsedArduTestLine(kind=kind, fields=fields)


class ArduTestSession:
    """Collects the current ArduTest smoke-test serial output.

    This intentionally supports the temporary line format emitted by the
    in-progress Arduino library. The protocol-spec implementation can replace
    this reader without changing the public fixture shape.
    """

    def __init__(self, dut: Any, *, timeout: float = 30.0) -> None:
        self.dut = dut
        self.timeout = timeout
        self.results: list[ArduTestResult] = []

    def run(self, name: str | None = None) -> list[ArduTestResult]:
        self.results = []
        version = self._expect_begin()
        test_count = self._expect_test_count()

        for _ in range(test_count):
            self.results.append(self._collect_one_result())

        selected_results = self.results
        if name is not None:
            selected_results = [result for result in self.results if result.name == name]
            if not selected_results:
                available = ", ".join(result.name for result in self.results) or "(none)"
                raise ArduTestError(f"unknown ArduTest test: {name}. Available tests: {available}")

        failed = [result for result in selected_results if result.status != "passed"]
        if failed:
            raise AssertionError(self._format_failure(version, failed))

        return selected_results

    def _expect_begin(self) -> str:
        line = self._read_line()
        parsed = parse_ardutest_line(line)
        if parsed.kind != "BEGIN":
            raise ArduTestError(f"expected ArduTest BEGIN, got: ARDUTEST {line}")
        if not parsed.fields:
            raise ArduTestError("ArduTest BEGIN did not include a version")
        return parsed.fields

    def _expect_test_count(self) -> int:
        line = self._read_line()
        parsed = parse_ardutest_line(line)
        if parsed.kind != "TESTS":
            raise ArduTestError(f"expected ArduTest TESTS, got: ARDUTEST {line}")
        try:
            return int(parsed.fields)
        except ValueError as e:
            raise ArduTestError(f"invalid ArduTest test count: {parsed.fields}") from e

    def _collect_one_result(self) -> ArduTestResult:
        line = self._read_line()
        parsed = parse_ardutest_line(line)
        if parsed.kind != "RUN":
            raise ArduTestError(f"expected ArduTest RUN, got: ARDUTEST {line}")
        test_name = parsed.fields
        events: list[ArduTestEvent] = []

        while True:
            line = self._read_line()
            parsed = parse_ardutest_line(line)
            if parsed.kind == "RESULT":
                result_name, status = self._parse_result_fields(parsed.fields)
                if result_name != test_name:
                    raise ArduTestError(
                        f"ArduTest result name mismatch: running {test_name}, got result for {result_name}"
                    )
                if status not in ("passed", "failed", "error"):
                    raise ArduTestError(f"invalid ArduTest status for {result_name}: {status}")
                return ArduTestResult(name=test_name, status=status, events=events)

            event_name, message = self._parse_event_fields(parsed.fields)
            events.append(ArduTestEvent(kind=parsed.kind, test_name=event_name, message=message))

    def _read_line(self) -> str:
        match = self.dut.expect(ARDUTEST_LINE_RE, timeout=self.timeout)
        value = match.group(1)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    @staticmethod
    def _parse_result_fields(fields: str) -> tuple[str, str]:
        parts = fields.split(" ", 1)
        if len(parts) != 2:
            raise ArduTestError(f"invalid ArduTest RESULT fields: {fields}")
        return parts[0], parts[1]

    @staticmethod
    def _parse_event_fields(fields: str) -> tuple[str | None, str]:
        parts = fields.split(" ", 1)
        if len(parts) == 1:
            return None, parts[0]
        return parts[0], parts[1]

    @staticmethod
    def _format_failure(version: str, failed: list[ArduTestResult]) -> str:
        lines = [f"ArduTest {version} reported failing tests:"]
        for result in failed:
            lines.append(f"- {result.name}: {result.status}")
            for event in result.events:
                if event.kind in {"FAIL", "FAIL_EQ", "ERROR"}:
                    lines.append(f"  {event.kind}: {event.message}")
        return "\n".join(lines)


def _split_name_value(message: str) -> tuple[str, str]:
    parts = message.split(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _parse_metric_value(value: str) -> int | float | str:
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
