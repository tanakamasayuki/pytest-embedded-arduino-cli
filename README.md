# pytest-embedded-arduino-cli

[日本語版 README](README.ja.md)

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
uv run pytest tests/my_app --port /dev/ttyACM0
```

Select an Arduino CLI profile from `sketch.yaml`:

```bash
uv run pytest tests/my_app --profile esp32s3 --port /dev/ttyACM0
```

Build only:

```bash
uv run pytest tests/my_app --run-mode=build
```

Upload and test against an already-built image:

```bash
uv run pytest tests/my_app --run-mode=test --port /dev/ttyACM0
```

`--run-mode=test` skips compile, reuses the existing build output, uploads it, and then runs the test.

Run this package's own tests:

```bash
uv run pytest
```

## Main Options

- `--run-mode=all|build|test`
- `--profile`

Use `pytest-embedded` standard options for runtime control, such as:

- `--port`
- `--flash-port`
- `--baud`
- `--embedded-services`

`pytest-embedded-serial` is installed as a normal dependency so hardware tests can use the serial service without extra package installation.
If `--embedded-services` is not specified, this plugin enables `serial` by default.

For command visibility, follow pytest's standard verbosity:

- `-v` shows the `arduino-cli compile` / `arduino-cli upload` command line
- `-vv` also shows execution context such as `cwd`, `sketch_dir`, `build_path`, `profile`, and `port`

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

## What This Plugin Does Not Try To Be

- A drop-in replacement for `pytest-embedded-arduino`
- An ESP-specific flashing layer
- A board auto-discovery tool

## Future Extensions

- Board-family-specific upload strategies
- Smarter artifact discovery
- Serial reset / monitor helpers
- Multi-device support
- Optional `fqbn` or sketch path overrides
