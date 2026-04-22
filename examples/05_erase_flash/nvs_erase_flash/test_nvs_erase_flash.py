def test_nvs_erase_flash_counter_resets(dut):
    dut.expect_exact("BOOT_COUNT 1")
