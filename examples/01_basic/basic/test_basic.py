import time

import pexpect
import pytest


STARTUP_TIMEOUT = 60.0
PROBE_INTERVAL = 0.5


def test_ping(dut):
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        dut.write("ping\n")
        try:
            dut.expect_exact("PONG", timeout=min(PROBE_INTERVAL, remaining))
            return
        except pexpect.TIMEOUT:
            continue
    pytest.fail(f"device did not answer PONG within {STARTUP_TIMEOUT} seconds")
