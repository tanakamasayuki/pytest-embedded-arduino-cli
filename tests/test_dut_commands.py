from __future__ import annotations

import os
from pathlib import Path
import socket
import threading
import time

import pexpect
import pytest

from pytest_embedded_arduino_cli.dut_commands import (
    DutCommand,
    DutCommandContext,
    DutCommandError,
    DutCommandSet,
    run_start_round,
    run_teardown_round,
    send_command,
    unescape,
)

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

START = DutCommand("START", b"\x01", "READY")
RECOVER = DutCommand("RECOVER", b"\x18", "RECOVERED")
STOP = DutCommand("STOP", b"\x04", "STOPPED")


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


class FakeQueue:
    def __init__(self) -> None:
        self.items: list[bytes] = []

    def put(self, item: bytes) -> None:
        self.items.append(item)


class FakeDut:
    """Records writes; replies once ``reply_after`` writes have been seen."""

    def __init__(self, label: str = "dut", reply_after: int = 1, sequence: list[str] | None = None) -> None:
        self.label = label
        self.reply_after = reply_after
        self.sequence = sequence
        self.writes: list[bytes] = []
        self.expects: list[tuple[str, float | None]] = []
        self._q = FakeQueue()

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        if self.sequence is not None:
            self.sequence.append(f"{self.label}:{data!r}")

    def expect_exact(self, pattern: str, timeout: float | None = None) -> None:
        self.expects.append((pattern, timeout))
        if len(self.writes) >= self.reply_after:
            return
        raise pexpect.TIMEOUT("no reply")


class FakeConfig:
    def __init__(self, ini: dict[str, str] | None = None, start_timeout: float = 15.0, teardown_timeout: float = 2.0):
        self.ini = {"arduino_cli_dut_command_terminator": "\\n", **(ini or {})}
        self.options = {
            "arduino_cli_dut_start_timeout": start_timeout,
            "arduino_cli_dut_teardown_timeout": teardown_timeout,
        }

    def getini(self, name: str) -> str:
        return self.ini.get(name, "")

    def getoption(self, name: str):
        return self.options[name]


def _commands(**kwargs) -> DutCommandSet:
    return DutCommandSet(**kwargs)


def _ctx(commands: DutCommandSet, *, phase: str = "teardown", stop: bool = False, failed: bool = False, timeout: float = 1.0):
    return DutCommandContext(
        phase=phase,
        stop=stop,
        session_end=stop,
        interrupted=False,
        failed=failed,
        timeout=timeout,
        commands=commands,
    )


# ---------------------------------------------------------------------------
# unescape / config
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\\x01", b"\x01"),
        ("\\x18\\x04", b"\x18\x04"),
        ("\\n", b"\n"),
        ("\\r\\n", b"\r\n"),
        ("READY", b"READY"),
        ("a\\\\b", b"a\\b"),
        ("\\t", b"\t"),
    ],
)
def test_unescape(text: str, expected: bytes) -> None:
    assert unescape(text) == expected


@pytest.mark.parametrize("text", ["\\xZZ", "\\x1", "\\q"])
def test_unescape_rejects_invalid_escapes(text: str) -> None:
    with pytest.raises(ValueError):
        unescape(text)


def test_command_set_is_disabled_when_nothing_is_configured() -> None:
    commands = DutCommandSet.from_config(FakeConfig())

    assert commands.start is None
    assert commands.recover is None
    assert commands.stop is None
    assert commands.terminator == b"\n"
    assert commands.enabled_names == []
    assert not commands.teardown_enabled


def test_command_set_reads_each_pair_independently() -> None:
    commands = DutCommandSet.from_config(
        FakeConfig(
            {
                "arduino_cli_dut_start_command": "\\x01",
                "arduino_cli_dut_start_reply": "READY",
                "arduino_cli_dut_stop_command": "\\x04",
                "arduino_cli_dut_stop_reply": "STOPPED",
                "arduino_cli_dut_command_terminator": "\\r\\n",
            },
            start_timeout=7.5,
            teardown_timeout=0.5,
        )
    )

    assert commands.start == DutCommand("START", b"\x01", "READY")
    assert commands.recover is None
    assert commands.stop == DutCommand("STOP", b"\x04", "STOPPED")
    assert commands.terminator == b"\r\n"
    assert commands.start_timeout == 7.5
    assert commands.teardown_timeout == 0.5
    assert commands.enabled_names == ["START", "STOP"]
    assert commands.teardown_enabled


def test_command_set_requires_command_and_reply_together() -> None:
    with pytest.raises(pytest.UsageError, match="must be configured together"):
        DutCommandSet.from_config(FakeConfig({"arduino_cli_dut_recover_command": "\\x18"}))


def test_command_set_reports_invalid_escapes_as_usage_error() -> None:
    with pytest.raises(pytest.UsageError, match="invalid value"):
        DutCommandSet.from_config(
            FakeConfig({"arduino_cli_dut_recover_command": "\\xZZ", "arduino_cli_dut_recover_reply": "OK"})
        )


# ---------------------------------------------------------------------------
# send_command
# ---------------------------------------------------------------------------


def test_send_command_appends_terminator_and_logs_marker() -> None:
    dut = FakeDut()

    send_command(dut, START, terminator=b"\n", timeout=1.0, resend_interval=None, target="primary")

    assert dut.writes == [b"\x01\n"]
    assert dut.expects[0][0] == "READY"
    assert dut._q.items == [b"[arduino-cli] START -> primary\n"]


def test_send_command_resends_until_the_reply_arrives() -> None:
    dut = FakeDut(reply_after=3)

    send_command(dut, START, terminator=b"\n", timeout=5.0, resend_interval=0.01, target="primary")

    assert dut.writes == [b"\x01\n"] * 3


def test_send_command_raises_after_the_budget_when_resending() -> None:
    dut = FakeDut(reply_after=10**6)

    with pytest.raises(DutCommandError, match=r"peer echo did not reply 'READY' to START .* within 0\.1s"):
        send_command(dut, START, terminator=b"\n", timeout=0.1, resend_interval=0.01, target="peer echo")

    assert len(dut.writes) > 1


def test_send_command_without_resend_writes_once() -> None:
    dut = FakeDut(reply_after=10**6)

    with pytest.raises(DutCommandError, match="RECOVER"):
        send_command(dut, RECOVER, terminator=b"\n", timeout=0.05, resend_interval=None, target="primary")

    assert dut.writes == [b"\x18\n"]


# ---------------------------------------------------------------------------
# start round
# ---------------------------------------------------------------------------


def test_start_round_sends_to_peers_in_name_order_then_primary() -> None:
    sequence: list[str] = []
    dut = FakeDut("primary", sequence=sequence)
    peers = {"echo": FakeDut("echo", sequence=sequence), "bridge": FakeDut("bridge", sequence=sequence)}

    run_start_round(dut, peers, _ctx(_commands(start=START), phase="start"))

    assert sequence == ["bridge:b'\\x01\\n'", "echo:b'\\x01\\n'", "primary:b'\\x01\\n'"]


def test_start_round_is_noop_without_start_command() -> None:
    dut = FakeDut()

    run_start_round(dut, {}, _ctx(_commands(recover=RECOVER), phase="start"))

    assert dut.writes == []


def test_start_round_propagates_missing_reply() -> None:
    dut = FakeDut(reply_after=10**6)

    with pytest.raises(DutCommandError, match="primary did not reply"):
        run_start_round(dut, {}, _ctx(_commands(start=START), phase="start", timeout=0.05))


def test_start_round_uses_module_override_instead_of_generic() -> None:
    dut = FakeDut()
    seen: list[tuple] = []

    def override(d, peers, ctx):
        seen.append((d, dict(peers), ctx.phase))

    run_start_round(dut, {"echo": FakeDut("echo")}, _ctx(_commands(start=START), phase="start"), override=override)

    assert seen[0][0] is dut
    assert list(seen[0][1]) == ["echo"]
    assert seen[0][2] == "start"
    assert dut.writes == []


def test_context_send_helpers_report_unconfigured_commands() -> None:
    ctx = _ctx(_commands(start=START), phase="start")

    with pytest.raises(DutCommandError, match="RECOVER is not configured"):
        ctx.send_recover(FakeDut())


# ---------------------------------------------------------------------------
# teardown round
# ---------------------------------------------------------------------------


def test_teardown_round_sends_recover_to_primary_then_peers_in_reverse_order() -> None:
    sequence: list[str] = []
    dut = FakeDut("primary", sequence=sequence)
    peers = {"bridge": FakeDut("bridge", sequence=sequence), "echo": FakeDut("echo", sequence=sequence)}

    run_teardown_round(dut, peers, _ctx(_commands(recover=RECOVER, stop=STOP), stop=False))

    assert sequence == ["primary:b'\\x18\\n'", "echo:b'\\x18\\n'", "bridge:b'\\x18\\n'"]


def test_teardown_round_sends_stop_when_nothing_runs_afterwards() -> None:
    dut = FakeDut()

    run_teardown_round(dut, {}, _ctx(_commands(recover=RECOVER, stop=STOP), stop=True))

    assert dut.writes == [b"\x04\n"]


def test_teardown_round_falls_back_to_recover_when_stop_is_not_configured() -> None:
    dut = FakeDut()

    run_teardown_round(dut, {}, _ctx(_commands(recover=RECOVER), stop=True))

    assert dut.writes == [b"\x18\n"]


def test_teardown_round_sends_nothing_on_ordinary_path_with_stop_only() -> None:
    dut = FakeDut()

    run_teardown_round(dut, {}, _ctx(_commands(stop=STOP), stop=False))

    assert dut.writes == []


def test_teardown_round_warns_and_continues_when_a_device_does_not_reply() -> None:
    dut = FakeDut("primary", reply_after=10**6)
    peer = FakeDut("echo")

    with pytest.warns(pytest.PytestWarning, match="RECOVER to primary failed"):
        run_teardown_round(dut, {"echo": peer}, _ctx(_commands(recover=RECOVER), timeout=0.05))

    assert peer.writes == [b"\x18\n"]


def test_teardown_round_turns_override_exceptions_into_warnings() -> None:
    def override(d, peers, ctx):
        raise RuntimeError("boom")

    with pytest.warns(pytest.PytestWarning, match="override failed: boom"):
        run_teardown_round(FakeDut(), {}, _ctx(_commands(recover=RECOVER)), override=override)


# ---------------------------------------------------------------------------
# integration over socket:// with the real pytest-embedded fixtures
# ---------------------------------------------------------------------------


COMMAND_REPLIES = {
    b"\x01": ("START", "READY"),
    b"\x18": ("RECOVER", "RECOVERED"),
    b"\x04": ("STOP", "STOPPED"),
}


class CommandServer:
    """TCP stand-in for a sketch: answers reserved bytes and echoes other lines."""

    def __init__(self, label: str, events: list[tuple[str, str]], replies: dict[bytes, tuple[str, str]]):
        self.label = label
        self.events = events
        self.replies = replies
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def url(self) -> str:
        return f"socket://127.0.0.1:{self.port}"

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        line = b""
        with conn:
            while True:
                try:
                    data = conn.recv(1024)
                except OSError:
                    return
                if not data:
                    return
                for value in data:
                    byte = bytes([value])
                    if byte in self.replies:
                        name, reply = self.replies[byte]
                        self.events.append((self.label, name))
                        conn.sendall(reply.encode() + b"\n")
                    elif byte == b"\n":
                        if line:
                            self.events.append((self.label, f"line:{line.decode(errors='replace')}"))
                            conn.sendall(b"ECHO " + line + b"\n")
                        line = b""
                    else:
                        line += byte

    def close(self) -> None:
        self.sock.close()


@pytest.fixture
def command_events() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def make_server(command_events: list[tuple[str, str]]):
    servers: list[CommandServer] = []

    def factory(label: str, replies: dict[bytes, tuple[str, str]] = COMMAND_REPLIES) -> CommandServer:
        server = CommandServer(label, command_events, replies)
        servers.append(server)
        return server

    yield factory
    for server in servers:
        server.close()


FAKE_ARDUINO_CONFTEST = """
from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.flasher import ArduinoCliUploadConfig


def _fake_compile(self, *, check=True):
    self.build_path.mkdir(parents=True, exist_ok=True)
    return None


def _fake_upload(self, *, check=True):
    return None


ArduinoCliBuildConfig.compile = _fake_compile
ArduinoCliUploadConfig.upload = _fake_upload
"""

FULL_INI = """
[pytest]
arduino_cli_dut_start_command = \\x01
arduino_cli_dut_start_reply = READY
arduino_cli_dut_recover_command = \\x18
arduino_cli_dut_recover_reply = RECOVERED
arduino_cli_dut_stop_command = \\x04
arduino_cli_dut_stop_reply = STOPPED
"""


def _make_sketch(pytester: pytest.Pytester, *, with_peer: bool = False) -> Path:
    test_dir = pytester.path / "sample_app"
    test_dir.mkdir()
    (test_dir / "sample_app.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
    (test_dir / "sketch.yaml").write_text("default_profile: host\nprofiles:\n  host: {}\n", encoding="utf-8")
    if with_peer:
        peer_dir = test_dir / "peer_echo"
        peer_dir.mkdir()
        (peer_dir / "peer_echo.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
        (peer_dir / "sketch.yaml").write_text("default_profile: host\nprofiles:\n  host: {}\n", encoding="utf-8")
    pytester.makeconftest(FAKE_ARDUINO_CONFTEST)
    return test_dir


def _run(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, test_file: Path, *args: str):
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(SRC_DIR), os.environ.get("PYTHONPATH")])))
    return pytester.runpytest_subprocess(
        str(test_file),
        "-p",
        "no:embedded-arduino-cli",
        "-p",
        "pytest_embedded_arduino_cli.plugin",
        f"--root-logdir={pytester.path / 'logs'}",
        "--arduino-cli-dut-teardown-timeout=3",
        *args,
    )


def _wait_for_events(events: list[tuple[str, str]], count: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while len(events) < count and time.monotonic() < deadline:
        time.sleep(0.02)


def test_lifecycle_commands_run_over_a_real_dut_connection(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, make_server, command_events
) -> None:
    server = make_server("primary")
    test_dir = _make_sketch(pytester)
    pytester.makeini(FULL_INI)
    (test_dir / "test_sample.py").write_text(
        """
def test_first(dut):
    dut.write("hello\\n")
    dut.expect_exact("ECHO hello")


def test_second(dut):
    pass
""",
        encoding="utf-8",
    )

    result = _run(pytester, monkeypatch, test_dir / "test_sample.py", f"--port={server.url}")

    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines(["*arduino-cli dut commands: START, RECOVER, STOP*"])
    _wait_for_events(command_events, 5)
    assert command_events == [
        ("primary", "START"),
        ("primary", "line:hello"),
        ("primary", "RECOVER"),
        ("primary", "START"),
        ("primary", "STOP"),
    ]
    logs = list((pytester.path / "logs").rglob("dut.log"))
    assert logs, "pytest-embedded did not write a dut.log"
    assert any("[arduino-cli] STOP -> primary" in log.read_text(errors="replace") for log in logs)


def test_lifecycle_commands_order_peers_before_primary_on_start_and_after_on_stop(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, make_server, command_events
) -> None:
    primary = make_server("primary")
    peer = make_server("peer")
    test_dir = _make_sketch(pytester, with_peer=True)
    pytester.makeini(FULL_INI)
    (test_dir / "test_sample.py").write_text(
        """
def test_pair(dut, peers):
    assert "echo" in peers
""",
        encoding="utf-8",
    )

    result = _run(
        pytester,
        monkeypatch,
        test_dir / "test_sample.py",
        f"--port={primary.url}",
        f"--peer-port=echo:{peer.url}",
    )

    result.assert_outcomes(passed=1)
    _wait_for_events(command_events, 4)
    assert command_events == [
        ("peer", "START"),
        ("primary", "START"),
        ("primary", "STOP"),
        ("peer", "STOP"),
    ]


def test_start_without_reply_is_a_setup_error_and_teardown_still_runs(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, make_server, command_events
) -> None:
    silent_on_start = {key: value for key, value in COMMAND_REPLIES.items() if key != b"\x01"}
    server = make_server("primary", silent_on_start)
    test_dir = _make_sketch(pytester)
    pytester.makeini(FULL_INI)
    (test_dir / "test_sample.py").write_text(
        """
def test_never_runs(dut):
    raise AssertionError("test body must not run")
""",
        encoding="utf-8",
    )

    result = _run(
        pytester,
        monkeypatch,
        test_dir / "test_sample.py",
        f"--port={server.url}",
        "--arduino-cli-dut-start-timeout=1",
    )

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*primary did not reply 'READY' to START*within 1.0s*"])
    _wait_for_events(command_events, 2)
    assert ("primary", "STOP") in command_events
    assert all(name != "line:test body must not run" for _, name in command_events)


def test_module_overrides_replace_the_generic_commands(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, make_server, command_events
) -> None:
    server = make_server("primary")
    test_dir = _make_sketch(pytester)
    pytester.makeini(FULL_INI)
    (test_dir / "test_sample.py").write_text(
        """
def arduino_cli_dut_start(dut, peers, ctx):
    dut.write(f"custom-start phase={ctx.phase}\\n")
    dut.expect_exact("ECHO custom-start", timeout=ctx.timeout)


def arduino_cli_dut_teardown(dut, peers, ctx):
    dut.write(f"custom-teardown stop={ctx.stop} failed={ctx.failed}\\n")
    dut.expect_exact("ECHO custom-teardown", timeout=ctx.timeout)


def test_fails(dut):
    assert False


def test_passes(dut):
    pass
""",
        encoding="utf-8",
    )

    result = _run(pytester, monkeypatch, test_dir / "test_sample.py", f"--port={server.url}")

    result.assert_outcomes(passed=1, failed=1)
    _wait_for_events(command_events, 4)
    assert command_events == [
        ("primary", "line:custom-start phase=start"),
        ("primary", "line:custom-teardown stop=False failed=True"),
        ("primary", "line:custom-start phase=start"),
        ("primary", "line:custom-teardown stop=True failed=False"),
    ]


def test_nothing_is_sent_when_no_command_is_configured(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, make_server, command_events
) -> None:
    server = make_server("primary")
    test_dir = _make_sketch(pytester)
    (test_dir / "test_sample.py").write_text(
        """
def test_plain(dut):
    dut.write("hello\\n")
    dut.expect_exact("ECHO hello")
""",
        encoding="utf-8",
    )

    result = _run(pytester, monkeypatch, test_dir / "test_sample.py", f"--port={server.url}")

    result.assert_outcomes(passed=1)
    assert "arduino-cli dut commands" not in result.stdout.str()
    _wait_for_events(command_events, 1)
    assert command_events == [("primary", "line:hello")]
