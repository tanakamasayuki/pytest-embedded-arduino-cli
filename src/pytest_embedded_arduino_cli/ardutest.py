from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
import time
from typing import Any, Literal


ArduTestStatus = Literal["passed", "failed", "skipped", "error"]


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
    skip_reason: str | None = None

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

    def __init__(self, dut: Any, *, timeout: float = 30.0, environ: dict[str, str] | None = None) -> None:
        self.dut = dut
        self.timeout = timeout
        self.environ = environ if environ is not None else os.environ
        self.results: list[ArduTestResult] = []
        self._tests: list[ArduTestCase] | None = None

    def run(self, name: str | None = None) -> list[ArduTestResult]:
        return self._run_protocol(name)

    def list_tests(self) -> list[ArduTestCase]:
        if self._tests is not None:
            return self._tests

        self._sync_hello()
        self._tests = self._list_tests_after_hello()
        return self._tests

    @property
    def logs(self) -> dict[str, list[str]]:
        return {result.name: result.logs for result in self.results}

    @property
    def metrics(self) -> dict[str, dict[str, list[int | float | str]]]:
        return {result.name: result.metrics for result in self.results}

    @property
    def artifacts(self) -> dict[str, dict[str, str]]:
        return {result.name: result.artifacts for result in self.results}

    def _list_tests_after_hello(self) -> list[ArduTestCase]:
        self._send_command("AT > LIST")

        tests: list[ArduTestCase] = []
        by_name: dict[str, ArduTestCase] = {}
        while True:
            parsed = self._read_protocol_line()
            if parsed.kind in {"READY", "HELLO"}:
                continue
            if parsed.kind == "ERROR":
                code, message = self._read_error_payload(parsed.fields)
                raise ArduTestError(f"ArduTest protocol error: {code}: {message}")
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
        by_name = {test.name: test for test in tests}
        runnable_tests: list[ArduTestCase] = []
        for test_name in selected_names:
            test = by_name[test_name]
            skip_reason = self._skip_reason(test)
            if skip_reason:
                self.results.append(ArduTestResult(name=test_name, status="skipped", skip_reason=skip_reason))
                continue
            runnable_tests.append(test)

        self._apply_configs(runnable_tests)

        for test in runnable_tests:
            test_name = test.name
            self._send_command(f"AT > RUN {test_name}")
            self.results.append(self._collect_one_protocol_result(test_name))

        failed = [result for result in self.results if result.status not in ("passed", "skipped")]
        if failed:
            raise AssertionError(self._format_failure("protocol", failed))

        return self.results

    def _skip_reason(self, test: ArduTestCase) -> str | None:
        missing_requirements = [name for name in test.requirements if not self._capability_enabled(name)]
        if missing_requirements:
            return "missing capability: " + ", ".join(missing_requirements)

        missing_configs = [name for name in test.required_configs if self._config_value(name) is None]
        if missing_configs:
            return "missing config: " + ", ".join(missing_configs)

        return None

    def _apply_configs(self, tests: list[ArduTestCase]) -> None:
        config_names: list[str] = []
        for test in tests:
            for name in test.required_configs:
                if name not in config_names:
                    config_names.append(name)

        if not config_names:
            return

        self._send_command("AT > CLEAR_CONFIG")
        for name in config_names:
            value = self._config_value(name)
            if value is None:
                continue
            self._send_payload_command("SET_CONFIG", name, value)

    def _capability_enabled(self, name: str) -> bool:
        value = self.environ.get("ARDUINO_TEST_CAP_" + _env_name(name))
        if value is None:
            return False
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
        raise ArduTestError(f"invalid capability value for {name}: {value}")

    def _config_value(self, name: str) -> str | None:
        return self.environ.get("ARDUINO_TEST_CONFIG_" + _env_name(name))

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
                code, message = self._read_error_payload(parsed.fields)
                raise ArduTestError(f"ArduTest protocol error: {code}: {message}")

            if parsed.kind not in {"LOG", "METRIC", "ARTIFACT_TEXT", "FAIL"}:
                raise ArduTestError(f"unexpected ArduTest event while running {test_name}: AT < {parsed.kind}")
            event = self._read_event(parsed)
            if event.test_name not in (None, test_name):
                raise ArduTestError(f"ArduTest event name mismatch: running {test_name}, got event for {event.test_name}")
            events.append(event)

    def _read_protocol_line(self) -> ParsedArduTestLine:
        match = self.dut.expect(ARDUTEST_PROTOCOL_LINE_RE, timeout=self.timeout)
        value = match.group(1)
        if isinstance(value, bytes):
            line = value.decode("utf-8", errors="replace")
        else:
            line = str(value)
        return parse_ardutest_line(line)

    def _read_payload(self, length: int) -> str:
        if length < 0:
            raise ArduTestError(f"invalid ArduTest payload length: {length}")
        if length == 0:
            return ""

        pattern = re.compile(rb"(?s)(.{%d})" % length)
        match = self.dut.expect(pattern, timeout=self.timeout)
        value = match.group(1)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    def _read_event(self, parsed: ParsedArduTestLine) -> ArduTestEvent:
        if parsed.kind == "LOG":
            test_name, length = self._parse_test_payload_header(parsed.kind, parsed.fields)
            return ArduTestEvent(kind=parsed.kind, test_name=test_name, message=self._read_payload(length))

        if parsed.kind == "ARTIFACT_TEXT":
            test_name, filename, _content_type, length = self._parse_artifact_payload_header(parsed.fields)
            return ArduTestEvent(kind=parsed.kind, test_name=test_name, message=f"{filename} {self._read_payload(length)}")

        if parsed.kind == "FAIL":
            test_name, file_name, line, length = self._parse_fail_payload_header(parsed.fields)
            return ArduTestEvent(
                kind=parsed.kind,
                test_name=test_name,
                message=f"{file_name}:{line} {self._read_payload(length)}",
            )

        event_name, message = self._parse_event_fields(parsed.fields)
        return ArduTestEvent(kind=parsed.kind, test_name=event_name, message=message)

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
                time.sleep(0.1)
                self._send_command("AT > HELLO 1")
                time.sleep(0.1)
                self._send_command("AT > HELLO 1")
                continue
            raise ArduTestError(f"expected ArduTest protocol HELLO, got: AT < {parsed.kind} {parsed.fields}")

    def _send_command(self, command: str) -> None:
        self.dut.write(f"{command}\n")

    def _send_payload_command(self, command: str, name: str, value: str) -> None:
        length = len(value.encode("utf-8"))
        self.dut.write(f"AT > {command} {name} {length}\n{value}")

    def _read_error_payload(self, fields: str) -> tuple[str, str]:
        parts = fields.split(" ", 1)
        if len(parts) != 2:
            raise ArduTestError(f"invalid ArduTest ERROR fields: {fields}")
        return parts[0], self._read_payload(self._parse_length(parts[1], "ERROR"))

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
    def _parse_length(value: str, kind: str) -> int:
        try:
            length = int(value)
        except ValueError as e:
            raise ArduTestError(f"invalid ArduTest {kind} payload length: {value}") from e
        if length < 0:
            raise ArduTestError(f"invalid ArduTest {kind} payload length: {value}")
        return length

    @classmethod
    def _parse_test_payload_header(cls, kind: str, fields: str) -> tuple[str | None, int]:
        parts = fields.split(" ", 1)
        if len(parts) != 2:
            raise ArduTestError(f"invalid ArduTest {kind} fields: {fields}")
        test_name = None if parts[0] == "-" else parts[0]
        return test_name, cls._parse_length(parts[1], kind)

    @classmethod
    def _parse_artifact_payload_header(cls, fields: str) -> tuple[str | None, str, str, int]:
        parts = fields.split(" ", 3)
        if len(parts) != 4:
            raise ArduTestError(f"invalid ArduTest ARTIFACT_TEXT fields: {fields}")
        test_name = None if parts[0] == "-" else parts[0]
        return test_name, parts[1], parts[2], cls._parse_length(parts[3], "ARTIFACT_TEXT")

    @classmethod
    def _parse_fail_payload_header(cls, fields: str) -> tuple[str | None, str, int, int]:
        parts = fields.split(" ", 3)
        if len(parts) != 4:
            raise ArduTestError(f"invalid ArduTest FAIL fields: {fields}")
        test_name = None if parts[0] == "-" else parts[0]
        try:
            line = int(parts[2])
        except ValueError as e:
            raise ArduTestError(f"invalid ArduTest FAIL line: {parts[2]}") from e
        return test_name, parts[1], line, cls._parse_length(parts[3], "FAIL")

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


def _env_name(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name).upper()
