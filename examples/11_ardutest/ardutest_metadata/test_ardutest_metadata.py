def test_ardutest_metadata(arduino_test):
    arduino_test.set_capability("measurement.current")
    arduino_test.set_config("sample_rate", 1000)

    tests = arduino_test.list_tests()

    assert tests[0].name == "test_sample_rate"
    assert tests[0].requirements == ("measurement.current",)
    assert tests[0].required_configs == ("sample_rate",)

    result = arduino_test.run("test_sample_rate")[0]

    assert result.logs == ["received sample_rate"]
    assert result.metrics == {"sample_rate": [1000]}
    assert result.artifacts == {"sample_rate.txt": "1000"}
