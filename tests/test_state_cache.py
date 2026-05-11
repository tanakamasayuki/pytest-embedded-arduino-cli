"""Tests for state_cache module."""

from datetime import datetime
from pathlib import Path
import json
import tempfile

import pytest

from pytest_embedded_arduino_cli.state_cache import StateCache, TestResult


class TestStateCache:
    """Test state cache functionality."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary directory for cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_init_state_structure(self):
        """Test initial state structure."""
        cache = StateCache(".pytest-results")
        state = cache._init_state()

        assert state["schema_version"] == 1
        assert "updated_at" in state
        assert state["profiles"] == {}

    def test_load_nonexistent_state(self, temp_cache_dir):
        """Test loading state when file does not exist."""
        cache = StateCache(temp_cache_dir / "nonexistent")
        state = cache.load_state()

        assert state["schema_version"] == 1
        assert "updated_at" in state
        assert state["profiles"] == {}

    def test_save_and_load_state(self, temp_cache_dir):
        """Test saving and loading state."""
        cache = StateCache(temp_cache_dir)
        cache.ensure_dir_exists()

        original_state = cache._init_state()
        cache.update_test_result(
            original_state,
            "uno",
            "tests/test_gpio.py::test_led",
            "passed",
        )
        cache.save_state(original_state)

        # Load and verify
        loaded_state = cache.load_state()
        assert loaded_state["schema_version"] == 1
        assert "uno" in loaded_state["profiles"]
        assert "tests/test_gpio.py::test_led" in loaded_state["profiles"]["uno"]["tests"]
        assert (
            loaded_state["profiles"]["uno"]["tests"]["tests/test_gpio.py::test_led"][
                "last_result"
            ]
            == "passed"
        )

    def test_update_test_result_pass(self, temp_cache_dir):
        """Test updating test result on pass."""
        cache = StateCache(temp_cache_dir)
        state = cache._init_state()

        cache.update_test_result(state, "esp32", "tests/test_wifi.py::test_connect", "passed")

        result = state["profiles"]["esp32"]["tests"]["tests/test_wifi.py::test_connect"]
        assert result["last_result"] == "passed"
        assert "last_run_at" in result
        assert "last_success_at" in result
        assert result["last_run_at"] == result["last_success_at"]

    def test_update_test_result_fail_preserves_last_success(self, temp_cache_dir):
        """Test that fail preserves previous last_success_at."""
        cache = StateCache(temp_cache_dir)
        state = cache._init_state()

        # First pass
        cache.update_test_result(state, "uno", "tests/test.py::test_1", "passed")
        first_success_at = state["profiles"]["uno"]["tests"]["tests/test.py::test_1"][
            "last_success_at"
        ]

        # Then fail
        cache.update_test_result(state, "uno", "tests/test.py::test_1", "failed")

        result = state["profiles"]["uno"]["tests"]["tests/test.py::test_1"]
        assert result["last_result"] == "failed"
        assert result["last_success_at"] == first_success_at

    def test_update_test_result_first_failure_no_success_at(self):
        """Test that first failure has no last_success_at."""
        cache = StateCache(".pytest-results")
        state = cache._init_state()

        cache.update_test_result(state, "board1", "tests/test_new.py::test_new", "failed")

        result = state["profiles"]["board1"]["tests"]["tests/test_new.py::test_new"]
        assert result["last_result"] == "failed"
        assert "last_run_at" in result
        assert "last_success_at" not in result

    def test_multiple_profiles(self, temp_cache_dir):
        """Test handling multiple profiles."""
        cache = StateCache(temp_cache_dir)
        state = cache._init_state()

        cache.update_test_result(state, "uno", "tests/test.py::test_1", "passed")
        cache.update_test_result(state, "esp32", "tests/test.py::test_1", "failed")

        assert "uno" in state["profiles"]
        assert "esp32" in state["profiles"]
        assert state["profiles"]["uno"]["tests"]["tests/test.py::test_1"]["last_result"] == "passed"
        assert (
            state["profiles"]["esp32"]["tests"]["tests/test.py::test_1"]["last_result"] == "failed"
        )

    def test_iso8601_format(self):
        """Test that ISO8601 format is used."""
        cache = StateCache(".pytest-results")
        iso_str = cache._current_iso8601()

        # Should be able to parse as ISO8601
        dt = datetime.fromisoformat(iso_str)
        assert dt is not None

    def test_state_file_readable_json(self, temp_cache_dir):
        """Test that saved state is readable JSON."""
        cache = StateCache(temp_cache_dir)
        cache.ensure_dir_exists()

        state = cache._init_state()
        cache.update_test_result(state, "board", "test.py::test", "passed")
        cache.save_state(state)

        # Read file directly and verify JSON validity
        with (temp_cache_dir / "state.json").open("r") as f:
            loaded = json.load(f)

        assert loaded["schema_version"] == 1
        assert "profiles" in loaded

    def test_corrupt_state_file_returns_fresh_state(self, temp_cache_dir):
        """Test that corrupt state file causes fresh state to be returned."""
        cache = StateCache(temp_cache_dir)
        cache.ensure_dir_exists()

        # Write corrupt JSON
        (temp_cache_dir / "state.json").write_text("{ invalid json")

        state = cache.load_state()
        assert state["schema_version"] == 1
        assert state["profiles"] == {}

    def test_ensure_dir_creates_directory(self, temp_cache_dir):
        """Test that ensure_dir_exists creates directory."""
        cache = StateCache(temp_cache_dir / "new" / "nested" / "dir")
        assert not cache.save_dir.exists()

        cache.ensure_dir_exists()
        assert cache.save_dir.exists()
        assert cache.save_dir.is_dir()
