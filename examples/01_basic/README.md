# 01_basic

[日本語版 (Japanese)](README.ja.md)

This is the smallest sample to try first and the runnable in-repository counterpart of [Your First Test](../../FIRST_TEST.md).

- The default profile is `esp32`
- Use `--profile` explicitly when you want another target such as `uno`
- The actual sketch lives under `basic/`

This sample defines `default_profile: esp32`, so it also works without `--profile`.

Some boards cannot receive text immediately after startup even though the serial port can already be opened. Pytest can also miss text that the sketch prints only once at startup. A test that assumes either one-shot exchange can therefore fail even when the sketch is healthy.

This test instead uses a readiness handshake: pytest repeatedly sends `ping` and checks the sketch's `PONG` response. It succeeds after bidirectional communication actually works, without depending on any particular startup attempt being delivered. A successful run reports `1 passed`. [Your First Test](../../FIRST_TEST.md#do-not-test-startup-serial-traffic-as-if-it-were-immediately-reliable) explains the timeout design in detail.

Example:

```bash
uv run pytest examples/01_basic --profile=esp32 --port=/dev/ttyUSB0
```

You can also target the sketch directory directly.

```bash
uv run pytest examples/01_basic/basic --profile=esp32 --port=/dev/ttyUSB0
```

Example with another profile:

```bash
uv run pytest examples/01_basic --profile uno --port=/dev/ttyACM0
```

This sample also demonstrates port resolution from environment variables.

- Use `TEST_SERIAL_PORT` for the common default
- Use `TEST_SERIAL_PORT_<PROFILE>` for profile-specific values
- Profile-specific variable names are derived by uppercasing the profile and replacing `-` with `_`

Examples:

```bash
export TEST_SERIAL_PORT=/dev/ttyUSB0
uv run pytest examples/01_basic
```

```bash
export TEST_SERIAL_PORT_UNO=/dev/ttyACM0
uv run pytest examples/01_basic --profile uno
```

For example, `esp32-s3` becomes `TEST_SERIAL_PORT_ESP32_S3`.

You can also inject variables from an env file:

```bash
uv run --env-file .env pytest examples/01_basic
```

Use [`examples/.env.example`](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli/blob/main/examples/.env.example) as the template.
Because the template lives under `examples/`, copy it to the repository root as `.env` before editing it:

```bash
cp examples/.env.example .env
```

After copying, update the values in `.env` to match your environment.
