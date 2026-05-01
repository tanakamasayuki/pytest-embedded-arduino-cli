def test_ardutest_metadata(monkeypatch, arduino_test):
    monkeypatch.setenv("ARDUINO_TEST_CAP_MEASUREMENT_CURRENT", "true")
    monkeypatch.setenv("ARDUINO_TEST_CONFIG_SAMPLE_RATE", "1000")

    tests = arduino_test.list_tests()

    assert tests[0].name == "test_sample_rate"
    assert tests[0].requirements == ("measurement.current",)
    assert tests[0].required_configs == ("sample_rate",)

    result = arduino_test.run("test_sample_rate")[0]

    assert result.logs == ["received sample_rate"]
    assert result.metrics == {"sample_rate": [1000]}
    assert result.artifacts == {"sample_rate.txt": "1000"}
