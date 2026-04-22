# 03_dut_input

This sample demonstrates passing values to the device at runtime through `dut`.

- The default profile is `esp32`
- Use `--profile` explicitly when selecting `uno`
- The sketch waits for input on serial, so the same flow works on both boards

This sample defines `default_profile: esp32`, so it also works without `--profile`.

This is the alternative to `02_env_define`.
Use this approach when you do not want to embed a value into the firmware image, for example when handling sensitive information.

Example:

```bash
uv run pytest examples/03_dut_input --port=/dev/ttyUSB0
```

Example with another profile:

```bash
uv run pytest examples/03_dut_input --profile uno --port=/dev/ttyACM0
```

The test waits for `READY`, sends a line through `dut.write(...)`, and then verifies the reply from the device.

The actual sketch lives under `serial_dut_input/`.
