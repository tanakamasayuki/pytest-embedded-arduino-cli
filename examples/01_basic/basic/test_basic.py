def test_hello_from_arduino(dut):
    dut.expect_exact("hello from arduino")
