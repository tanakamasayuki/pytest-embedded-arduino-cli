import re

def test_unity_runner_executes_library_tests(dut):
    dut.expect(re.compile(rb"2 Tests 0 Failures 0 Ignored"))
    dut.expect_exact("OK")
