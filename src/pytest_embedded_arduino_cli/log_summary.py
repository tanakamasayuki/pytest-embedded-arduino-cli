"""Write human-readable result markers into the pytest-embedded log directory.

pytest-embedded creates ``<tmpdir>/pytest-embedded/<utc-timestamp>/<test name>/``
and drops ``dut.log`` there. Reading that tree tells you nothing about whether the
tests passed, so this module adds:

* ``<status>.txt`` inside each test directory (``PASSED.txt``, ``FAILED.txt``, ...)
  holding the test id, timings and the failure text when there is one.
* a zero-byte marker at the session root whose *name* carries the counts,
  e.g. ``FAILED-2_PASSED-7``, so ``tree``/``ls`` shows the outcome on one line.
* ``SUMMARY.txt`` and ``summary.json`` with the whole run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import shlex
from typing import Any

import pytest

# Largest failure text kept in a marker file; the tail is what matters.
_MAX_FAILURE_CHARS = 32 * 1024

# Statuses ordered worst-first. Used both for the root marker name and to pick a
# single status when several test ids share one directory name.
_STATUS_ORDER = (
    "ERROR",
    "FAILED",
    "XPASSED",
    "PASSED",
    "XFAILED",
    "SKIPPED",
)
_STATUS_RANK = {status: index for index, status in enumerate(_STATUS_ORDER)}


@dataclass
class _Phase:
    outcome: str
    duration: float
    longrepr: str | None
    wasxfail: bool


@dataclass
class _TestRecord:
    nodeid: str
    name: str
    profile: str | None = None
    phases: dict[str, _Phase] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return sum(phase.duration for phase in self.phases.values())

    @property
    def status(self) -> str:
        for when in ("setup", "teardown"):
            phase = self.phases.get(when)
            if phase is not None and phase.outcome == "failed":
                return "ERROR"

        call = self.phases.get("call")
        if call is not None:
            if call.outcome == "failed":
                return "FAILED"
            if call.outcome == "skipped":
                return "XFAILED" if call.wasxfail else "SKIPPED"
            if call.outcome == "passed":
                return "XPASSED" if call.wasxfail else "PASSED"

        setup = self.phases.get("setup")
        if setup is not None and setup.outcome == "skipped":
            return "SKIPPED"
        return "SKIPPED"

    @property
    def failure_text(self) -> tuple[str, str] | None:
        """Return ``(phase name, text)`` for the phase that explains the outcome."""
        for when in ("call", "setup", "teardown"):
            phase = self.phases.get(when)
            if phase is None or not phase.longrepr:
                continue
            if phase.outcome in ("failed", "skipped"):
                return when, phase.longrepr
        return None


class LogSummaryCollector:
    """Accumulates reports during the session and writes the files at the end."""

    def __init__(self) -> None:
        self._records: dict[str, _TestRecord] = {}

    def record(self, report: pytest.TestReport, profile: str | None) -> None:
        record = self._records.get(report.nodeid)
        if record is None:
            record = _TestRecord(nodeid=report.nodeid, name=_test_dir_name(report.nodeid))
            self._records[report.nodeid] = record
        if profile is not None:
            record.profile = profile

        record.phases[report.when or "call"] = _Phase(
            outcome=report.outcome,
            duration=float(getattr(report, "duration", 0.0) or 0.0),
            longrepr=_longrepr_text(report),
            wasxfail=hasattr(report, "wasxfail"),
        )

    def write(self, session_tempdir: Path, session: pytest.Session, exitstatus: int) -> None:
        if not self._records:
            return
        session_tempdir.mkdir(parents=True, exist_ok=True)

        # Several test ids can share a directory name (same function name in two
        # files, as pytest-embedded names directories after the function alone).
        by_dir: dict[str, list[_TestRecord]] = {}
        for record in self._records.values():
            by_dir.setdefault(record.name, []).append(record)

        for dir_name, records in sorted(by_dir.items()):
            test_dir = _safe_subdir(session_tempdir, dir_name)
            if test_dir is None:
                continue
            self._write_test_marker(test_dir, records)

        records_sorted = sorted(self._records.values(), key=lambda r: r.nodeid)
        counts = _count_statuses(records_sorted)
        _write_root_marker(session_tempdir, counts)
        (session_tempdir / "SUMMARY.txt").write_text(
            _render_summary(records_sorted, counts, session, exitstatus, session_tempdir),
            encoding="utf-8",
        )
        (session_tempdir / "summary.json").write_text(
            json.dumps(
                _summary_payload(records_sorted, counts, session, exitstatus, session_tempdir),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_test_marker(self, test_dir: Path, records: list[_TestRecord]) -> None:
        status = min((record.status for record in records), key=lambda s: _STATUS_RANK.get(s, len(_STATUS_ORDER)))
        test_dir.mkdir(parents=True, exist_ok=True)

        # Only one status file per directory, so stale ones from a reused
        # directory never contradict the current run.
        for name in _STATUS_ORDER:
            stale = test_dir / f"{name}.txt"
            if name != status and stale.exists():
                stale.unlink()

        lines = [f"status: {status}"]
        for record in sorted(records, key=lambda r: r.nodeid):
            lines.append(f"test: {record.nodeid}")
            if len(records) > 1:
                lines.append(f"  status: {record.status}")
            lines.append(f"  duration: {_format_duration(record.duration)} ({_phase_durations(record)})")
            if record.profile:
                lines.append(f"  profile: {record.profile}")

        logs = sorted(path.name for path in test_dir.glob("*.log"))
        if logs:
            lines.append(f"logs: {', '.join(logs)}")

        for record in sorted(records, key=lambda r: r.nodeid):
            failure = record.failure_text
            if failure is None:
                continue
            when, text = failure
            lines.append("")
            lines.append(f"--- {record.nodeid} ({when}) ---")
            lines.append(_truncate_tail(text))

        (test_dir / f"{status}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _test_dir_name(nodeid: str) -> str:
    """pytest-embedded names the directory after ``request.node.name``."""
    return nodeid.split("::")[-1]


def _safe_subdir(root: Path, name: str) -> Path | None:
    """Resolve ``name`` under ``root``, refusing anything that escapes it."""
    if not name or name in (".", ".."):
        return None
    candidate = root / name
    try:
        candidate.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return candidate


def _longrepr_text(report: pytest.TestReport) -> str | None:
    wasxfail = getattr(report, "wasxfail", None)
    longrepr = getattr(report, "longrepr", None)
    if longrepr is None:
        return f"xfail: {wasxfail}" if wasxfail else None
    if isinstance(longrepr, tuple):
        # Skips arrive as (file, lineno, reason).
        return str(longrepr[-1])
    try:
        return str(longrepr)
    except Exception:
        return None


def _truncate_tail(text: str) -> str:
    if len(text) <= _MAX_FAILURE_CHARS:
        return text
    kept = text[-_MAX_FAILURE_CHARS:]
    dropped = len(text) - len(kept)
    return f"[... {dropped} characters dropped, showing the tail ...]\n{kept}"


def _format_duration(seconds: float) -> str:
    return f"{seconds:.2f}s"


def _phase_durations(record: _TestRecord) -> str:
    parts = [
        f"{when} {_format_duration(record.phases[when].duration)}"
        for when in ("setup", "call", "teardown")
        if when in record.phases
    ]
    return ", ".join(parts) if parts else "no phases"


def _count_statuses(records: list[_TestRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    return counts


def _root_marker_name(counts: dict[str, int]) -> str:
    parts = [f"{status}-{counts[status]}" for status in _STATUS_ORDER if counts.get(status)]
    return "_".join(parts) if parts else "NO-TESTS"


def _write_root_marker(session_tempdir: Path, counts: dict[str, int]) -> None:
    marker = _root_marker_name(counts)
    for existing in session_tempdir.iterdir():
        if existing.is_file() and existing.name != marker and _looks_like_root_marker(existing.name):
            existing.unlink()
    (session_tempdir / marker).touch()


def _looks_like_root_marker(name: str) -> bool:
    if name == "NO-TESTS":
        return True
    for part in name.split("_"):
        status, _, count = part.partition("-")
        if status not in _STATUS_RANK or not count.isdigit():
            return False
    return bool(name)


def _invocation_command(session: pytest.Session) -> str:
    try:
        args = list(session.config.invocation_params.args)
    except Exception:
        return ""
    return " ".join(["pytest", *(shlex.quote(arg) for arg in args)])


def _option(session: pytest.Session, name: str) -> Any:
    try:
        return session.config.getoption(name)
    except Exception:
        return None


def _render_summary(
    records: list[_TestRecord],
    counts: dict[str, int],
    session: pytest.Session,
    exitstatus: int,
    session_tempdir: Path,
) -> str:
    lines = [
        "pytest-embedded-arduino-cli run summary",
        f"generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"log dir: {session_tempdir}",
        f"exit status: {exitstatus}",
        f"result: {_root_marker_name(counts)}",
        f"total duration: {_format_duration(sum(record.duration for record in records))}",
        f"profile: {_option(session, 'profile') or 'default'}",
        f"run-mode: {_option(session, 'run_mode')}",
        f"rootdir: {session.config.rootpath}",
        f"command: {_invocation_command(session)}",
        "",
        f"{'result':<8} {'duration':>9}  test",
    ]
    for record in sorted(records, key=lambda r: (_STATUS_RANK.get(r.status, 99), r.nodeid)):
        lines.append(f"{record.status:<8} {_format_duration(record.duration):>9}  {record.nodeid}")

    failing = [
        record
        for record in sorted(records, key=lambda r: r.nodeid)
        if record.status in ("ERROR", "FAILED") and record.failure_text is not None
    ]
    if failing:
        lines.append("")
        lines.append("failures:")
        for record in failing:
            when, text = record.failure_text  # type: ignore[misc]
            lines.append(f"  {record.nodeid} ({when}) -> {record.name}/{record.status}.txt")
            for line in _truncate_tail(text).splitlines():
                lines.append(f"    {line}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _summary_payload(
    records: list[_TestRecord],
    counts: dict[str, int],
    session: pytest.Session,
    exitstatus: int,
    session_tempdir: Path,
) -> dict[str, Any]:
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "log_dir": str(session_tempdir),
        "exit_status": exitstatus,
        "result": _root_marker_name(counts),
        "counts": {status: counts[status] for status in _STATUS_ORDER if counts.get(status)},
        "profile": _option(session, "profile") or "default",
        "run_mode": _option(session, "run_mode"),
        "rootdir": str(session.config.rootpath),
        "command": _invocation_command(session),
        "total_duration": round(sum(record.duration for record in records), 3),
        "tests": [
            {
                "nodeid": record.nodeid,
                "dir": record.name,
                "status": record.status,
                "profile": record.profile,
                "duration": round(record.duration, 3),
                "phases": {
                    when: {"outcome": phase.outcome, "duration": round(phase.duration, 3)}
                    for when, phase in record.phases.items()
                },
                "message": (_truncate_tail(record.failure_text[1]) if record.failure_text else None),
            }
            for record in sorted(records, key=lambda r: r.nodeid)
        ],
    }
