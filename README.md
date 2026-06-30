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
- `--peer-profile=NAME:PROFILE`
- `--peer-port=NAME:PORT`
- `--clean`
- `--device-lock=auto|off|required`
- `--device-lock-timeout=SECONDS`
- `--device-lock-dir=PATH`
- `--device-lock-key=KEY`
- `--save-state`
- `--save-state-dir=PATH`
- `--arduino-test-timeout=SECONDS`
- `--arduino-test-artifact-dir=PATH`
- `--arduino-test-missing-config=skip|error`

`--clean` passes `--clean` to `arduino-cli compile`.
It is useful when Arduino CLI's incremental build cache should be ignored.
It also removes the ArduTest artifact directory before running.

`--save-state` enables local test verification state caching to `state.json` for development convenience.
By default, this is disabled.
When enabled, test results are recorded per profile in `.pytest-results/state.json` (or a custom directory specified with `--save-state-dir`).
This feature is useful during development to track which tests are passing/failing without relying on external CI systems.

Example:

```bash
uv run pytest tests/my_app --profile esp32 --port=/dev/ttyACM0 --save-state
```

State file structure (`.pytest-results/state.json`):

```json
{
  "schema_version": 1,
  "updated_at": "2026-05-11T12:00:00.123456+09:00",
  "profiles": {
    "esp32": {
      "tests": {
        "tests/my_app/test_my_app.py::test_something": {
          "last_result": "passed",
          "last_run_at": "2026-05-11T12:00:00.123456+09:00",
          "last_success_at": "2026-05-11T12:00:00.123456+09:00"
        }
      }
    }
  }
}
```

For peer tests (multi-DUT), only the primary DUT state is recorded.

`--save-state-dir` specifies the directory for state.json storage.
The default is `.pytest-results` (relative to pytest rootdir unless absolute).

`--arduino-test-artifact-dir` selects the ArduTest artifact root.
The default is `ardutest`, resolved relative to pytest's `rootdir`.
The directory is created only when an artifact is saved.

`--arduino-test-missing-config` controls required ArduTest config that is not provided.
The default is `skip`; use `error` when missing config should fail the pytest run.

`--device-lock` controls cross-process exclusion for physical DUTs.
The default is `auto`.
In `auto` mode, this plugin lets compile finish first, then waits for a device lock immediately before upload when a physical serial port such as `/dev/ttyUSB0`, `/dev/ttyACM0`, or `COM3` is resolved.
The lock is held until the DUT is no longer in use, so another pytest process cannot upload new firmware while a test is still running on that board.

Device locks are keyed by the resolved physical serial port, not by profile.
Peer DUTs use their own resolved ports and are locked together with the primary DUT in a deterministic order.
`socket://...` targets are not locked by default because they usually represent host-process or TCP/IP DUTs.
Use `--device-lock=off` to disable locking, `--device-lock=required` to fail when no lock key can be resolved, and `--device-lock-key=KEY` for unusual environments where the port string is not a stable physical-device identity.
The lock files live in a user runtime/cache directory by default and use OS file locking, so a leftover lock file after a forced termination does not by itself keep the device locked.

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

## Peer DUTs

Tests that need additional DUTs can place `peer_<name>/` sketch directories next to the primary sketch.
The primary sketch remains available as `dut`; peer sketches are available through the `peers` fixture.

```text
tests/
  my_app/
    sketch.yaml
    my_app.ino
    test_my_app.py
    peer_echo/
      sketch.yaml
      peer_echo.ino
```

```python
def test_with_peer(dut, peers):
    echo = peers["echo"]

    dut.expect_exact("MAIN_READY")
    echo.expect_exact("ECHO_READY")
```

Peer DUTs are prepared only for tests that request the `peers` fixture.
If a test uses only `dut`, `peer_*` directories are ignored for that test.
Requesting `peers` enables all detected peer DUTs; `peers["<name>"]` is the mapping API for accessing the connected peer.

Startup order is fixed:

1. the primary DUT is built and uploaded first
2. peer DUTs are built and uploaded later, in peer name order
3. peer DUTs are connected and exposed through `peers`
4. the primary DUT is connected and exposed as `dut`

On real serial hardware, short boot-time messages can be missed if a sketch prints them immediately after reset or upload.
Host Arduino core socket runs often keep enough output for this not to matter, but hardware tests should use a startup delay, repeated READY message, or an explicit handshake from Python before relying on early output.

`sketch.yaml` is not extended for peer configuration.
Each peer directory is a normal sketch directory with its own `.ino` and `sketch.yaml`.

Peer profiles are resolved in this order:

1. `--peer-profile <name>:<profile>`
2. `default_profile` in `peer_<name>/sketch.yaml`
3. Skip the peer test if no profile is resolved

`--profile` is for the primary DUT only and is not inherited by peer DUTs.
Peer DUTs also do not use single-profile auto-selection.
If a peer should run without `--peer-profile`, define `default_profile` in that peer's `sketch.yaml`.

Peer ports are resolved in this order:

1. `--peer-port <name>:<port>`
2. `TEST_SERIAL_PORT_PEER_<NAME>_<PROFILE>`
3. `TEST_SERIAL_PORT_PEER_<NAME>`
4. `profiles.<PROFILE>.port` in the peer `sketch.yaml`, only when it is a `socket://...` URL
5. Skip the peer test if no port is resolved

`--peer-profile` and `--peer-port` may be specified multiple times.
Use one option per peer instead of comma-separated values.

```bash
uv run pytest tests/my_app \
  --profile esp32 \
  --peer-profile echo:host \
  --peer-port echo:socket://localhost
```

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

The plugin injects these defines/flags through `arduino-cli compile --build-property <property>=...` and auto-selects an empty property so board-defined flags are not overwritten. It prefers `build.extra_flags`, then `build.defines`; if ESP32 board options occupy both, it falls back to empty C/C++ compile flag properties such as `compiler.cpp.extra_flags` and `compiler.c.extra_flags`. You can pin the property explicitly to skip the detection probe (about one second faster):

```toml
build_property = "build.defines"        # all profiles

[profiles.esp32]
build_property = "build.defines"        # per-profile override
```

For command visibility, follow pytest's standard verbosity:

- `-v` shows the `arduino-cli compile` / `arduino-cli upload` command line
- `-vv` also shows execution context such as `cwd`, `sketch_dir`, `build_path`, `profile`, and `port`

### Capturing the full serial log

`dut.expect(...)` stops reading as soon as the pattern matches, so bytes the device sends *after* the matched line are not guaranteed to reach the `dut.log` file — it can end mid-line. This is a capture-timing effect, not a device fault: the log file and the live `-s` console are fed from the same stream, and the tail in flight can be lost when the DUT is closed.

The plugin already drains the receive buffer on a best-effort basis when the serial connection closes, which usually brings `dut.log` up to roughly what `-s` shows. It is not a full guarantee. When you need the complete trailing output deterministically:

- Have the device print an end-of-output marker as its last line and `expect` it, so reading naturally extends to the true end:

  ```python
  dut.expect_exact("=== END ===")
  ```

- Or drain explicitly before the test finishes:

  ```python
  import pexpect

  dut.expect_exact("last line I care about")
  dut.expect(pexpect.TIMEOUT, timeout=2)  # read whatever still arrives
  ```

Note that `arduino_test.run()` stops reading at the ArduTest `RESULT` event, so any `LOG` / tick lines the device emits after `RESULT` are not collected unless you drain afterwards.

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

Use fixture methods for fixed test-local ArduTest values:

```python
def test_sample_rate(arduino_test):
    arduino_test.set_capability("measurement.current")
    arduino_test.set_config("sample_rate", 1000)
    arduino_test.run("test_sample_rate")
```

Use environment variables, `.env`, or CI variables for values that depend on the machine, board, lab setup, or secrets.

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
  - Minimal examples for using the experimental `arduino_test` fixture with the ArduTest Arduino library
  - Detailed protocol/API and artifact-saving tests live in the ArduTest test suite: https://github.com/tanakamasayuki/ArduTest/tree/main/tests

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
