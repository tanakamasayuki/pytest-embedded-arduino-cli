import re

import pytest


def test_env_define_gets_ip_address(dut, pytestconfig):
    if pytestconfig.getoption("profile") == "uno":
        pytest.skip("Environment define example requires an ESP32-class profile")

    match = dut.expect(
        [
            re.compile(rb"WIFI_OK ((\d{1,3}\.){3}\d{1,3})"),
            re.compile(rb"WIFI_ERROR ([^\r\n]+)"),
        ],
        timeout=60,
    )

    if match.re.pattern.startswith(b"WIFI_ERROR"):
        raise AssertionError(f"Wi-Fi connection failed: {match.group(1).decode()}")
