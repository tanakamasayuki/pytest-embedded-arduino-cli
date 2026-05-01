# pytest-embedded-arduino-cli

[日本語版 README](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli/blob/main/README.ja.md)

A pytest plugin to test Arduino projects using `pytest-embedded` and `arduino-cli`.

## Overview

`pytest-embedded-arduino-cli` is a small plugin that keeps `pytest-embedded`'s generic DUT / serial / expect flow and replaces Arduino-specific build and upload with `arduino-cli`.

This package does not depend on `pytest-embedded-arduino`. It is intended to stay generic enough to work well for Arduino projects beyond ESP32-specific assumptions.

## Design

- Build with `arduino-cli compile`
- Upload with `arduino-cli upload`
- Use `pytest-embedded` as the runtime foundation
- Avoid `EspSerial` and ESP-specific flashing services
- Resolve sketch settings from `sketch.yaml` and `--profile`
- Treat the test file directory as the sketch directory

## Setup

```bash
uv init
uv add pytest-embedded-arduino-cli
uv sync
```

Runtime dependencies include:

- `pytest`
- `pytest-embedded`
- `pytest-embedded-serial`
- `PyYAML`

## Requirements

- `arduino-cli` available in `PATH`
- Installed Arduino board core(s)
- A serial port accessible from the host when running hardware tests

When `sketch.yaml` declares platform or library versions, Arduino CLI resolves them through its local package and library indexes.
The indexes do not need to be refreshed on every test run, but they should be updated periodically or before CI/release verification.
If a build fails because a declared platform or library version cannot be found, try:

```bash
arduino-cli core update-index
arduino-cli lib update-index
```

## Project Layout

The expected layout is one sketch directory per test app.

```text
tests/
  my_app/
    sketch.yaml
    my_app.ino
    test_my_app.py
```

When pytest runs a specific `.py` file, this plugin treats that file's directory as the sketch directory. Build settings are resolved from the nearest `sketch.yaml`.

## Usage

Build, upload, and run tests:

```bash
uv run pytest tests/my_app --port=/dev/ttyACM0
```

Select an Arduino CLI profile from `sketch.yaml`:

```bash
uv run pytest tests/my_app --profile esp32s3 --port=/dev/ttyACM0
```

Build only:

```bash
uv run pytest tests/my_app --run-mode=build
```

Force a clean Arduino CLI compile:

```bash
uv run pytest tests/my_app --clean
```

Upload and test against an already-built image:

```bash
uv run pytest tests/my_app --run-mode=test --port=/dev/ttyACM0
```

`--run-mode=test` skips compile, reuses the existing build output, uploads it, and then runs the test.

Run this package's own tests:

```bash
uv run pytest
```

## Main Options

- `--run-mode=all|build|test`
- `--profile`
- `--clean`
- `--arduino-test-timeout=SECONDS`

`--clean` passes `--clean` to `arduino-cli compile`.
It is useful when Arduino CLI's incremental build cache should be ignored.

Use `pytest-embedded` standard options for runtime control, such as:

- `--port`
- `--flash-port`
- `--baud`
- `--embedded-services`

`pytest-embedded-serial` is installed as a normal dependency so hardware tests can use the serial service without extra package installation.
If `--embedded-services` is not specified, this plugin enables `serial` by default.

For profile-specific serial ports, the plugin resolves ports in this order:

1. `--flash-port`
2. `--port`
3. `TEST_SERIAL_PORT_<PROFILE>`
4. `TEST_SERIAL_PORT`
5. `profiles.<PROFILE>.port` in `sketch.yaml`, only when it is a `socket://...` URL

Because of how `pytest` parses arguments, options that take path-like values such as `--port` and `--flash-port` are safer when written with `=`, for example `--port=/dev/ttyUSB0`.
Depending on the environment, `uv run pytest --port /dev/ttyUSB0` may cause that path to be interpreted as another base path.
If needed, `uv run pytest --rootdir . --port /dev/ttyUSB0` is also a valid workaround.

For targets that run on the host machine and expose the DUT over TCP/IP, use the URL format supported by `pytest-embedded-serial` / pyserial.
If the selected `sketch.yaml` profile defines `port: socket://localhost`, `--port=socket://localhost` can be omitted.

```bash
uv run pytest tests/my_app --profile host
```

When the port number is specified, such as `socket://localhost:56789`, the DUT connects to that socket directly.
When the port number is omitted, such as `socket://localhost`, the plugin is expected to read `port` from `*.host-arduino.json` generated under the build output directory and then connect to `socket://localhost:<port>`.
This resolution should prefer the host-arduino information file instead of capturing upload stdout.

```json
{
  "pid": 21228,
  "port": 56789
}
```

Host execution is an early, lightweight test path for pure logic and serial protocol checks without physical hardware.
Results may differ depending on the host OS, gcc or other toolchain versions, and the `Serial` class implementation provided by the host Arduino core, so this does not guarantee behavior on real hardware.
Use real hardware for peripherals, timing, interrupts, memory layout, Flash/NVS, and board-specific APIs.
Build success can also differ by board core and platform, so running build tests with the production board profile is still recommended.
For `socket://...` ports, this plugin batches serial reads to avoid the very slow one-byte-at-a-time redirect behavior that can otherwise appear with host Arduino cores.

Example:

```bash
export TEST_SERIAL_PORT_ESP32S3=/dev/ttyUSB1
uv run pytest tests/my_app --profile esp32s3
```

Profile resolution works as follows:

1. If `--profile` is specified, that profile is used
2. Otherwise, if `sketch.yaml` defines `default_profile`, that profile is used
3. Otherwise, if `sketch.yaml` has exactly one profile, it is selected automatically
4. Otherwise, pytest exits with an error because the profile is ambiguous

In practice, explicitly specifying `--profile` is recommended.
If you do not want to pass `--profile`, define `default_profile` in `sketch.yaml`.
The single-profile auto-selection is supported as a fallback, but it is better not to rely on it for regular project configuration.

For compile-time defines, place a `build_config.toml` in the sketch directory:

```toml
[defines]
TEST_WIFI_SSID = "WIFI_SSID"
TEST_WIFI_PASSWORD = "WIFI_PASSWORD"

[flags]
PYTEST_BUILD = true
ENABLE_TEST_HOOKS = true
```

In `[defines]`, the left side is the environment variable name and the right side is the C/C++ define name.
For example, `TEST_WIFI_SSID` becomes `-DWIFI_SSID="..."` at compile time.
`[flags]` is for value-less defines.
Only `true` entries are passed, such as `-DPYTEST_BUILD`; `false` entries are omitted.

Set values before running pytest:

```bash
export TEST_WIFI_SSID=my-ssid
export TEST_WIFI_PASSWORD=my-password
uv run pytest tests/my_app --port=/dev/ttyACM0
```

You can also load these values from a dotenv file through `uv run`.
`--env-file` is a `uv` option, so put it before `pytest`:

```bash
uv run --env-file .env pytest tests/my_app --port=/dev/ttyACM0
```

If an environment variable is missing, the plugin still passes the define with an empty string value.
This allows the test or sketch code to decide how to handle missing settings.
The plugin does not add test flags such as `PYTEST_BUILD` automatically.
Projects that need them should declare them explicitly under `[flags]`.

For command visibility, follow pytest's standard verbosity:

- `-v` shows the `arduino-cli compile` / `arduino-cli upload` command line
- `-vv` also shows execution context such as `cwd`, `sketch_dir`, `build_path`, `profile`, and `port`

## ArduTest Fixture

This package includes an experimental `arduino_test` fixture for sketches that use the separate Arduino-side ArduTest library.
ArduTest is expected to be declared by the sketch's `sketch.yaml`, with the library version pinned there for reproducible tests.
Detailed usage examples will be added under `examples/` after the API and protocol settle.

```python
def test_board(arduino_test):
    arduino_test.run()
```

`arduino_test.run()` fails the pytest test automatically when ArduTest reports a failed or error result.
Use additional assertions only when you want to check collected logs, metrics, artifacts, or metadata.

The current fixture speaks ArduTest protocol version `1`.

## Example

```python
def test_hello(dut):
    dut.expect_exact("hello from arduino")
```

```cpp
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("hello from arduino");
}

void loop() {}
```

Additional samples:

- `examples/01_basic`
  - Minimal hello-world example
  - Uses `esp32` as the default profile and also supports `uno`
  - Includes port resolution from `TEST_SERIAL_PORT` and `TEST_SERIAL_PORT_<PROFILE>`
- `examples/02_env_define`
  - Demonstrates compile-time defines from environment variables
  - Uses Wi-Fi on ESP32-class targets to explain `build_config.toml`
- `examples/03_dut_input`
  - Demonstrates runtime input over serial through `dut.write(...)`
  - Works on both `esp32` and `uno`
- `examples/04_unity_basic`
  - Demonstrates a minimal Unity-based test sketch for ESP32
- `examples/05_nvs_persistent`
  - Demonstrates that ESP32 `Preferences` / NVS data remains by default
  - Unsupported profiles are skipped before build because the example is specifically about ESP32 persistence
- `examples/06_erase_flash`
  - Demonstrates `EraseFlash=all` for resetting ESP32 persistent data before upload
  - Pairs with `05_nvs_persistent`
- `examples/07_arduino_library_project`
  - Demonstrates a practical Arduino library project with `tests/` as the `uv` root
  - Includes `run_wsl.sh` as a practical test workspace example
- `examples/08_arduino_ide_project`
  - Demonstrates an Arduino IDE style sketch project with `tests/` as the `uv` root
  - Uses thin wrapper `#include` files so the runner can reference sketch-side code that is not separated as a library
- `examples/09_host_arduino_core`
  - Demonstrates a board core that builds and runs the Arduino sketch on the host machine
  - Uses `port: socket://localhost` in `sketch.yaml` to connect to the TCP/IP endpoint opened by the host executable
  - Useful for simple pure-logic and serial-protocol checks, not a replacement for real hardware tests or build tests with the real board profile
- `examples/10_build_flags`
  - Demonstrates value-less compile-time defines with `[flags]` in `build_config.toml`
  - Shows how a project can explicitly enable test flags such as `PYTEST_BUILD`
- `examples/11_ardutest`
  - Demonstrates the experimental `arduino_test` fixture with the ArduTest Arduino library
  - Splits the basic runner and metadata/config runner so each sketch stays focused

Execution guidance for `examples/` is described in [examples/README.md](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli/blob/main/examples/README.md).

## Warnings

You may see `PytestExperimentalApiWarning: record_xml_attribute is an experimental feature`.

This warning comes from `pytest-embedded`, not from this plugin. It is usually safe to ignore.
If you want to suppress it in your project, add a warning filter in `pytest.ini`, `pyproject.toml`, or a local config such as `examples/pytest.ini`.

## What This Plugin Does Not Try To Be

- A drop-in replacement for `pytest-embedded-arduino`
- An ESP-specific flashing layer
- A board auto-discovery tool

## Future Extensions

- Board-family-specific upload strategies
- Smarter artifact discovery
- Serial reset / monitor helpers
- TCP/IP connection helpers for host Arduino cores
- Multi-device support
- Optional `fqbn` or sketch path overrides

## Release

This repository uses GitHub Actions for releases.

Before triggering a release:

- Update the `## Unreleased` section in `CHANGELOG.md`
- Make sure `uv run pytest tests` passes locally if needed

Release flow:

1. Open GitHub Actions
2. Run the `Release` workflow manually
3. Enter the release version such as `0.1.0`
4. Choose whether to publish to PyPI

The workflow will:

- Update versions in `pyproject.toml` and `src/pytest_embedded_arduino_cli/__init__.py`
- Move `CHANGELOG.md` unreleased entries into `## <version>`
- Run tests and build the package
- Commit the release changes and create tag `v<version>`
- Create a GitHub Release
- Publish to PyPI when enabled

PyPI publishing is configured for Trusted Publishing via GitHub Actions.
