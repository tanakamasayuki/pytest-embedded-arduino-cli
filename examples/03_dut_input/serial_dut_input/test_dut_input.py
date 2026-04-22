def test_dut_input_round_trip(dut):
    payload = "hello from pytest"

    dut.expect_exact("READY")
    dut.write(f"{payload}\n")
    dut.expect_exact(f"RECEIVED {payload}")
    dut.expect_exact("OK")
