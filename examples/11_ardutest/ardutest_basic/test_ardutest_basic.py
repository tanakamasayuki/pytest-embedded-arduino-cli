def test_ardutest_basic(arduino_test):
    arduino_test.run()

    # The protocol version is negotiated during HELLO and recorded on the session.
    assert arduino_test.device_protocol_version == "1"
    assert arduino_test.device_library == "ArduTest"

    # reset() sends RESET_STATE and re-synchronizes on the next run.
    arduino_test.reset()
    arduino_test.run()
