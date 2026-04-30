def test_build_flags_are_applied(dut):
    dut.expect_exact("PYTEST_BUILD enabled")
    dut.expect_exact("TEST_HOOKS enabled")
    dut.expect_exact("DISABLED_FLAG disabled")
