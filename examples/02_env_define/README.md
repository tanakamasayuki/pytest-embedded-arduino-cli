# 02_env_define

This sample demonstrates compile-time defines loaded from environment variables.

- The default profile is `esp32`
- Use `--profile` explicitly when selecting `esp32s3`
- This sample targets ESP32-class boards
- Unsupported profiles such as `uno` are not listed in `sketch.yaml` and are skipped before build if selected
- The sketch itself uses Wi-Fi, but the focus of the example is `build_config.toml`

This sample defines `default_profile: esp32`, so it also works without `--profile`.

Use this approach when the sketch needs values that differ by environment, such as a Wi-Fi AP name or an API key.

You can also pass such values at runtime over serial through `dut`, but that requires receive-side handling in the sketch, and serial-based setup can sometimes be less stable.
This example uses compile-time defines to avoid that extra runtime exchange.

Either approach is valid.
If embedding the value into the firmware is not acceptable, for example when handling sensitive information, pass it at runtime through `dut` instead.

Set environment variables before running it.

```bash
export TEST_WIFI_SSID=my-ssid
export TEST_WIFI_PASSWORD=my-password
uv run pytest examples/02_env_define --port /dev/ttyUSB0
```

You can also inject the same variables from an env file:

```bash
uv run --env-file .env pytest examples/02_env_define
```

Example with another profile:

```bash
export TEST_SERIAL_PORT_ESP32S3=/dev/ttyUSB1
uv run pytest examples/02_env_define --profile esp32s3
```

Profile-specific variable names follow the same rule as the plugin: uppercase the profile name and replace `-` with `_`.

Use [`examples/.env.example`](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli/blob/main/examples/.env.example) as the template.
Because the template lives under `examples/`, copy it to the repository root as `.env` before editing it:

```bash
cp examples/.env.example .env
```

After copying, update the values in `.env` to match your environment.

The actual sketch lives under `wifi_env_define/`.
