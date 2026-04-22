import re

import pytest


def test_nvs_persistent_counter(dut, pytestconfig):
    if pytestconfig.getoption("profile") == "uno":
        pytest.skip("NVS persistence example is specific to ESP32 Preferences")

    match = dut.expect(re.compile(rb"BOOT_COUNT (\d+)"))
    assert int(match.group(1)) >= 1
