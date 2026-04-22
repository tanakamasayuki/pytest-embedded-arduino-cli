def test_unity_wrapper_runner_executes_all_unity_tests(dut):
    dut.expect_unity_test_output(timeout=60)
