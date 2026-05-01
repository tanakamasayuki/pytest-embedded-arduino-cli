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


@dataclass(frozen=True)
class ArduTestCase:
    name: str
    requirements: tuple[str, ...] = ()
    required_configs: tuple[str, ...] = ()


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


ARDUTEST_PROTOCOL_LINE_RE = re.compile(rb"AT < ([^\r\n]+)\r?\n")


def parse_ardutest_line(line: str) -> ParsedArduTestLine:
    try:
        kind, fields = line.split(" ", 1)
    except ValueError:
        kind, fields = line, ""
    return ParsedArduTestLine(kind=kind, fields=fields)


class ArduTestSession:
    """Controls ArduTest over the line-based protocol."""

    def __init__(self, dut: Any, *, timeout: float = 30.0) -> None:
        self.dut = dut
        self.timeout = timeout
        self.results: list[ArduTestResult] = []

    def run(self, name: str | None = None) -> list[ArduTestResult]:
        return self._run_protocol(name)

    def list_tests(self) -> list[ArduTestCase]:
        self._sync_hello()
        return self._list_tests_after_hello()

    def _list_tests_after_hello(self) -> list[ArduTestCase]:
        self._send_command("AT > LIST")

        tests: list[ArduTestCase] = []
        by_name: dict[str, ArduTestCase] = {}
        while True:
            parsed = self._read_protocol_line()
            if parsed.kind in {"READY", "HELLO"}:
                continue
            if parsed.kind == "END_LIST":
                return tests
            if parsed.kind == "TEST":
                test = ArduTestCase(name=parsed.fields)
                tests.append(test)
                by_name[test.name] = test
                continue
            if parsed.kind in {"REQUIRE", "REQUIRE_CONFIG"}:
                test_name, value = self._parse_event_fields(parsed.fields)
                if test_name is None or test_name not in by_name:
                    raise ArduTestError(f"unknown ArduTest metadata target: AT < {parsed.kind} {parsed.fields}")
                current = by_name[test_name]
                if parsed.kind == "REQUIRE":
                    updated = ArduTestCase(
                        name=current.name,
                        requirements=(*current.requirements, value),
                        required_configs=current.required_configs,
                    )
                else:
                    updated = ArduTestCase(
                        name=current.name,
                        requirements=current.requirements,
                        required_configs=(*current.required_configs, value),
                    )
                by_name[test_name] = updated
                tests[tests.index(current)] = updated
                continue
            raise ArduTestError(f"expected ArduTest protocol metadata, got: AT < {parsed.kind} {parsed.fields}")

    def _run_protocol(self, name: str | None = None) -> list[ArduTestResult]:
        tests = self.list_tests()
        return self._run_protocol_tests(tests, name)

    def _run_protocol_tests(self, tests: list[ArduTestCase], name: str | None = None) -> list[ArduTestResult]:
        test_names = [test.name for test in tests]
        selected_names = test_names if name is None else [name]
        if name is not None and name not in test_names:
            available = ", ".join(test_names) or "(none)"
            raise ArduTestError(f"unknown ArduTest test: {name}. Available tests: {available}")

        self.results = []
        for test_name in selected_names:
            self._send_command(f"AT > RUN {test_name}")
            self.results.append(self._collect_one_protocol_result(test_name))

        failed = [result for result in self.results if result.status != "passed"]
        if failed:
            raise AssertionError(self._format_failure("protocol", failed))

        return self.results

    def _collect_one_protocol_result(self, test_name: str) -> ArduTestResult:
        running = self._read_protocol_line()
        if running.kind != "RUNNING" or running.fields != test_name:
            raise ArduTestError(f"expected AT < RUNNING {test_name}, got: AT < {running.kind} {running.fields}")

        events: list[ArduTestEvent] = []
        while True:
            parsed = self._read_protocol_line()
            if parsed.kind == "RESULT":
                result_name, status = self._parse_result_fields(parsed.fields)
                if result_name != test_name:
                    raise ArduTestError(
                        f"ArduTest result name mismatch: running {test_name}, got result for {result_name}"
                    )
                if status not in ("passed", "failed", "error"):
                    raise ArduTestError(f"invalid ArduTest status for {result_name}: {status}")
                return ArduTestResult(name=test_name, status=status, events=events)
            if parsed.kind == "ERROR":
                raise ArduTestError(f"ArduTest protocol error: {parsed.fields}")

            event_name, message = self._parse_event_fields(parsed.fields)
            events.append(ArduTestEvent(kind=parsed.kind, test_name=event_name, message=message))

    def _read_protocol_line(self) -> ParsedArduTestLine:
        match = self.dut.expect(ARDUTEST_PROTOCOL_LINE_RE, timeout=self.timeout)
        value = match.group(1)
        if isinstance(value, bytes):
            line = value.decode("utf-8", errors="replace")
        else:
            line = str(value)
        return parse_ardutest_line(line)

    def _expect_protocol_kind(self, kind: str) -> ParsedArduTestLine:
        parsed = self._read_protocol_line()
        if parsed.kind != kind:
            raise ArduTestError(f"expected ArduTest protocol {kind}, got: AT < {parsed.kind} {parsed.fields}")
        return parsed

    def _sync_hello(self) -> ParsedArduTestLine:
        self._send_command("AT > HELLO 1")
        while True:
            parsed = self._read_protocol_line()
            if parsed.kind == "HELLO":
                return parsed
            if parsed.kind == "READY":
                self._send_command("AT > HELLO 1")
                continue
            raise ArduTestError(f"expected ArduTest protocol HELLO, got: AT < {parsed.kind} {parsed.fields}")

    def _send_command(self, command: str) -> None:
        self.dut.write(f"{command}\n")

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
