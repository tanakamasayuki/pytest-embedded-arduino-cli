import re

def test_nvs_persistent_counter(dut):
    match = dut.expect(re.compile(rb"BOOT_COUNT (\d+)"))
    assert int(match.group(1)) >= 1
