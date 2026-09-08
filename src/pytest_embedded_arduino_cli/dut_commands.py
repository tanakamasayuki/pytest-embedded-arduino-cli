"""Reserved DUT lifecycle commands: START / RECOVER / STOP.

The plugin can send three reserved commands to the primary DUT and every
connected peer DUT so that the devices are in a known state at the edges of a
test:

- ``START`` after all fixtures are connected and before the test body runs
- ``RECOVER`` right before the serial connections close after every test
- ``STOP`` instead of ``RECOVER`` when nothing runs after this test in the
  session (last test, ``-x`` / ``--maxfail`` stop, Ctrl-C)

Each command is opt-in: it is active only when both its command bytes and its
reply line are configured in the pytest ini. A reply always means that the
sketch has reached the target state of that command, never that the command
was merely received.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import string
import time
from typing import Any, Callable, Mapping
import warnings

import pytest


#: Interval between START retransmissions while waiting for the reply.
START_RESEND_INTERVAL = 0.5

COMMAND_NAMES = ("start", "recover", "stop")

_SIMPLE_ESCAPES = {
    "n": b"\n",
    "r": b"\r",
    "t": b"\t",
    "0": b"\x00",
    "\\": b"\\",
}


class DutCommandError(RuntimeError):
    """Raised when a DUT does not acknowledge a lifecycle command in time."""


def unescape(text: str) -> bytes:
    """Decode the small escape language used in ini values.

    Supported escapes are ``\\xNN``, ``\\n``, ``\\r``, ``\\t``, ``\\0`` and
    ``\\\\``. Everything else is taken literally as UTF-8.
    """
    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != "\\" or i + 1 >= len(text):
            out += ch.encode("utf-8")
            i += 1
            continue
        nxt = text[i + 1]
        if nxt == "x":
            digits = text[i + 2 : i + 4]
            if len(digits) != 2 or any(c not in string.hexdigits for c in digits):
                raise ValueError(f"invalid \\x escape in {text!r}")
            out.append(int(digits, 16))
            i += 4
            continue
        if nxt in _SIMPLE_ESCAPES:
            out += _SIMPLE_ESCAPES[nxt]
            i += 2
            continue
        raise ValueError(f"unknown escape \\{nxt} in {text!r}")
    return bytes(out)


@dataclass(frozen=True)
class DutCommand:
    name: str
    command: bytes
    reply: str


@dataclass(frozen=True)
class DutCommandSet:
    start: DutCommand | None = None
    recover: DutCommand | None = None
    stop: DutCommand | None = None
    terminator: bytes = b"\n"
    start_timeout: float = 15.0
    teardown_timeout: float = 2.0

    @property
    def enabled_names(self) -> list[str]:
        return [name.upper() for name in COMMAND_NAMES if getattr(self, name) is not None]

    @property
    def teardown_enabled(self) -> bool:
        return self.recover is not None or self.stop is not None

    @classmethod
    def from_config(cls, config: Any) -> DutCommandSet:
        commands: dict[str, DutCommand | None] = {}
        for name in COMMAND_NAMES:
            command_key = f"arduino_cli_dut_{name}_command"
            reply_key = f"arduino_cli_dut_{name}_reply"
            command_text = (config.getini(command_key) or "").strip()
            reply_text = (config.getini(reply_key) or "").strip()
            if not command_text and not reply_text:
                commands[name] = None
                continue
            if not command_text or not reply_text:
                raise pytest.UsageError(f"{command_key} and {reply_key} must be configured together")
            try:
                command_bytes = unescape(command_text)
                reply = unescape(reply_text).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as e:
                raise pytest.UsageError(f"invalid value for {command_key} / {reply_key}: {e}") from e
            commands[name] = DutCommand(name.upper(), command_bytes, reply)

        terminator_text = config.getini("arduino_cli_dut_command_terminator")
        try:
            terminator = unescape(terminator_text) if terminator_text is not None else b"\n"
        except ValueError as e:
            raise pytest.UsageError(f"invalid value for arduino_cli_dut_command_terminator: {e}") from e

        return cls(
            start=commands["start"],
            recover=commands["recover"],
            stop=commands["stop"],
            terminator=terminator,
            start_timeout=float(config.getoption("arduino_cli_dut_start_timeout")),
            teardown_timeout=float(config.getoption("arduino_cli_dut_teardown_timeout")),
        )


def write_marker(dut: Any, text: str) -> None:
    """Put a marker line into the DUT log so the command is visible in ``dut.log``."""
    queue = getattr(dut, "_q", None)
    if queue is None:
        return
    try:
        queue.put(f"[arduino-cli] {text}\n".encode("utf-8"))
    except Exception:
        pass


def send_command(
    dut: Any,
    command: DutCommand,
    *,
    terminator: bytes,
    timeout: float,
    resend_interval: float | None,
    target: str,
) -> None:
    """Write ``command`` to ``dut`` and wait for its reply line.

    With ``resend_interval`` the command is retransmitted until the reply
    arrives or ``timeout`` elapses; without it the command is written once.
    """
    import pexpect

    payload = command.command + terminator
    write_marker(dut, f"{command.name} -> {target}")
    started = time.monotonic()
    deadline = started + timeout
    attempts = 0
    while True:
        dut.write(payload)
        attempts += 1
        if attempts > 1:
            logging.debug("arduino-cli: %s resent to %s (attempt %d)", command.name, target, attempts)
        remaining = max(deadline - time.monotonic(), 0.0)
        wait = remaining if resend_interval is None else min(resend_interval, remaining)
        try:
            dut.expect_exact(command.reply, timeout=wait)
        except pexpect.TIMEOUT:
            if resend_interval is None or time.monotonic() >= deadline:
                break
            continue
        if attempts > 1:
            logging.debug(
                "arduino-cli: %s acknowledged by %s after %d attempts (%.2fs)",
                command.name, target, attempts, time.monotonic() - started,
            )
        return
    raise DutCommandError(
        f"{target} did not reply {command.reply!r} to {command.name} ({command.command!r}) "
        f"within {timeout:.1f}s (sent {attempts} time{'s' if attempts != 1 else ''})"
    )


@dataclass
class DutCommandContext:
    """Context handed to the generic implementation and to module overrides."""

    phase: str
    stop: bool
    session_end: bool
    interrupted: bool
    failed: bool
    timeout: float
    commands: DutCommandSet = field(repr=False)

    def send_start(self, dut: Any, name: str = "primary") -> None:
        self._send(dut, self.commands.start, "start", name, resend=True)

    def send_recover(self, dut: Any, name: str = "primary") -> None:
        self._send(dut, self.commands.recover, "recover", name, resend=False)

    def send_stop(self, dut: Any, name: str = "primary") -> None:
        self._send(dut, self.commands.stop, "stop", name, resend=False)

    def _send(self, dut: Any, command: DutCommand | None, kind: str, name: str, *, resend: bool) -> None:
        if command is None:
            raise DutCommandError(f"{kind.upper()} is not configured (arduino_cli_dut_{kind}_command)")
        send_command(
            dut,
            command,
            terminator=self.commands.terminator,
            timeout=self.timeout,
            resend_interval=START_RESEND_INTERVAL if resend else None,
            target=name,
        )


Override = Callable[[Any, Mapping[str, Any], DutCommandContext], None]


def run_start_round(
    dut: Any | None,
    peers: Mapping[str, Any],
    ctx: DutCommandContext,
    override: Override | None = None,
) -> None:
    """Send START to every peer in name order, then to the primary DUT.

    Failures propagate so that pytest reports them as setup errors.
    """
    if override is not None:
        override(dut, peers, ctx)
        return
    if ctx.commands.start is None:
        return
    for name in sorted(peers):
        ctx.send_start(peers[name], name=f"peer {name}")
    if dut is not None:
        ctx.send_start(dut, name="primary")


def run_teardown_round(
    dut: Any | None,
    peers: Mapping[str, Any],
    ctx: DutCommandContext,
    override: Override | None = None,
) -> None:
    """Send STOP or RECOVER to the primary DUT, then to peers in reverse name order.

    Failures never change the test result; they are reported as warnings.
    """
    if override is not None:
        try:
            override(dut, peers, ctx)
        except Exception as e:
            _warn(f"arduino_cli_dut_teardown override failed: {e}")
        return

    if ctx.stop and ctx.commands.stop is not None:
        command = ctx.commands.stop
    else:
        command = ctx.commands.recover
    if command is None:
        return

    targets: list[tuple[str, Any]] = []
    if dut is not None:
        targets.append(("primary", dut))
    targets.extend((f"peer {name}", peers[name]) for name in sorted(peers, reverse=True))
    for target, device in targets:
        try:
            send_command(
                device,
                command,
                terminator=ctx.commands.terminator,
                timeout=ctx.timeout,
                resend_interval=None,
                target=target,
            )
        except Exception as e:
            _warn(f"{command.name} to {target} failed: {e}")


def _warn(message: str) -> None:
    warnings.warn(f"arduino-cli: {message}", pytest.PytestWarning, stacklevel=3)
