def test_peer_host_smoke_starts_primary_and_peer(dut, peers):
    echo = peers["echo"]

    dut.write("ready?\n")
    echo.write("ready?\n")

    dut.expect_exact("PEER_HOST_MAIN_READY")
    echo.expect_exact("PEER_HOST_ECHO_READY")
