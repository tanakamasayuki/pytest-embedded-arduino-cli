def test_unity_basic_executes(dut):
    dut.expect_unity_test_output(timeout=60)
