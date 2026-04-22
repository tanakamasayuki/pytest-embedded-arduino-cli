import re

import pytest


def test_unity_runner_executes_library_tests(dut, pytestconfig):
    if pytestconfig.getoption("profile") == "uno":
        pytest.skip("unity_runner uses the ESP32 Unity integration")

    dut.expect(re.compile(rb"2 Tests 0 Failures 0 Ignored"))
    dut.expect_exact("OK")
