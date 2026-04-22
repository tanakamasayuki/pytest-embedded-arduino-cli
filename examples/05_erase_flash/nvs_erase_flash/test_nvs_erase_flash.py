import pytest


def test_nvs_erase_flash_counter_resets(dut, pytestconfig):
    if pytestconfig.getoption("profile") == "uno":
        pytest.skip("Erase-flash example is specific to ESP32 Preferences")

    dut.expect_exact("BOOT_COUNT 1")
