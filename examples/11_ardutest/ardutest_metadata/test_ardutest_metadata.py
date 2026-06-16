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

    # Host-measured wall-clock duration is available for executed tests.
    assert result.duration is not None

    # artifact_files lists text and binary artifacts with content type and path.
    files = result.artifact_files
    assert [(a.filename, a.content_type, a.binary) for a in files] == [
        ("sample_rate.txt", "text/plain", False),
    ]
    assert files[0].path is not None
