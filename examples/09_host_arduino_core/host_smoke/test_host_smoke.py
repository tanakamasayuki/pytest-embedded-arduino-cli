def test_host_smoke_round_trip(dut):
    dut.expect_exact("HOST_SMOKE_READY")
    dut.write("ping\n")
    dut.expect_exact("HOST_SMOKE_ECHO ping")
