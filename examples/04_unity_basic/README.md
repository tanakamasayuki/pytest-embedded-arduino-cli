# 04_unity_basic

This sample demonstrates a minimal Unity-based test sketch for ESP32.

- The default profile is `esp32`
- This sample intentionally supports only ESP32-class targets
- It shows Unity itself, not an application-specific protocol over serial

You can test the same logic by printing text and checking it with `dut.expect(...)`,
but Unity simplifies the checking side because the framework formats the test result for you.
On the Python side, `dut.expect_unity_test_output(...)` is enough to validate the run.

ESP32 provides `unity.h` in its standard Arduino environment, so this sample works without adding an extra Unity library.
For boards such as `uno`, Unity is not available in the same way, so you would need to add and manage it separately if you want the same style.

Example:

```bash
uv run pytest -s examples/04_unity_basic --port=/dev/ttyUSB0
```

The sketch runs two Unity test cases on boot and prints the standard Unity summary.

The actual sketch lives under `unity_basic/`.
