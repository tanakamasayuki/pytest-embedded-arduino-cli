def test_ardutest_metadata(monkeypatch, arduino_test):
    monkeypatch.setenv("ARDUINO_TEST_CAP_MEASUREMENT_CURRENT", "true")
    monkeypatch.setenv("ARDUINO_TEST_CONFIG_SAMPLE_RATE", "1000")

    tests = arduino_test.list_tests()

    assert tests[0].name == "test_sample_rate"
    assert tests[0].requirements == ("measurement.current",)
    assert tests[0].required_configs == ("sample_rate",)

    results = arduino_test.run()

    assert [result.name for result in results] == ["test_sample_rate"]
    assert results[0].status == "passed"
    assert results[0].logs == ["received sample_rate"]
    assert results[0].metrics == {"sample_rate": [1000]}
    assert results[0].artifacts == {"sample_rate.txt": "1000"}
