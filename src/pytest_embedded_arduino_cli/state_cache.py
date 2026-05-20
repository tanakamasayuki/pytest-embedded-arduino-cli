from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class TestResult:
    """Single test result entry in state.json"""

    last_result: str  # passed, failed, error, etc.
    last_run_at: str  # ISO8601 format with timezone
    last_success_at: str | None = None  # ISO8601 format with timezone, or None


class StateCache:
    """Manages test state cache (state.json) for local development."""

    SCHEMA_VERSION = 1
    DEFAULT_DIR = ".pytest-results"
    STATE_FILENAME = "state.json"

    def __init__(self, save_dir: str | Path):
        """
        Initialize state cache manager.

        Args:
            save_dir: Directory to save state.json (relative to pytest rootdir or absolute)
        """
        self.save_dir = Path(save_dir)
        self.state_file = self.save_dir / self.STATE_FILENAME

    def ensure_dir_exists(self) -> None:
        """Create save directory if it does not exist."""
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict[str, Any]:
        """
        Load state.json if it exists, otherwise return empty initial structure.

        Returns:
            State dictionary with schema_version, updated_at, and profiles
        """
        if not self.state_file.exists():
            return self._init_state()

        try:
            with self.state_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, IOError):
            # If corrupt, return fresh state
            return self._init_state()

    def save_state(self, state: dict[str, Any]) -> None:
        """
        Save state dictionary to state.json.

        Args:
            state: State dictionary to save
        """
        self.ensure_dir_exists()
        state["updated_at"] = self._current_iso8601()
        self.sort_tests(state)

        # Write with indentation for readability
        with self.state_file.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def sort_tests(self, state: dict[str, Any]) -> None:
        """Sort test entries by nodeid while preserving the surrounding JSON order."""
        profiles = state.get("profiles")
        if not isinstance(profiles, dict):
            return

        for profile_state in profiles.values():
            if not isinstance(profile_state, dict):
                continue
            tests = profile_state.get("tests")
            if isinstance(tests, dict):
                profile_state["tests"] = dict(sorted(tests.items()))

    def update_test_result(
        self,
        state: dict[str, Any],
        profile: str,
        nodeid: str,
        result: str,
        last_success_at: str | None = None,
    ) -> None:
        """
        Update a single test result in state.

        Args:
            state: State dictionary to update (modified in place)
            profile: Profile name (e.g., "uno", "esp32")
            nodeid: pytest nodeid (e.g., "tests/test_gpio.py::test_led")
            result: Test result (e.g., "passed", "failed", "error")
            last_success_at: Previous success timestamp, or None if this is first pass/fail
        """
        if "profiles" not in state:
            state["profiles"] = {}

        if profile not in state["profiles"]:
            state["profiles"][profile] = {"tests": {}}

        if "tests" not in state["profiles"][profile]:
            state["profiles"][profile]["tests"] = {}

        now_iso = self._current_iso8601()
        tests = state["profiles"][profile]["tests"]

        if result == "passed":
            # Update all timestamps on pass
            tests[nodeid] = {
                "last_result": result,
                "last_run_at": now_iso,
                "last_success_at": now_iso,
            }
        else:
            # On fail/error, preserve previous last_success_at
            previous_success = None
            if nodeid in tests and "last_success_at" in tests[nodeid]:
                previous_success = tests[nodeid]["last_success_at"]

            tests[nodeid] = {
                "last_result": result,
                "last_run_at": now_iso,
            }
            if previous_success:
                tests[nodeid]["last_success_at"] = previous_success

    def _init_state(self) -> dict[str, Any]:
        """Create initial empty state structure."""
        return {
            "schema_version": self.SCHEMA_VERSION,
            "updated_at": self._current_iso8601(),
            "profiles": {},
        }

    @staticmethod
    def _current_iso8601() -> str:
        """Return current datetime in ISO8601 format with timezone."""
        return datetime.now().astimezone().isoformat()
