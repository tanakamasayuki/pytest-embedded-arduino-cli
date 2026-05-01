def test_ardutest_basic(arduino_test):
    results = arduino_test.run()

    assert [result.name for result in results] == [
        "test_true_passes",
        "test_numbers_match",
    ]
    assert all(result.status == "passed" for result in results)
    assert arduino_test.logs["test_true_passes"] == ["running test_true_passes"]
