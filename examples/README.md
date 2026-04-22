# examples

`examples/` contains runnable samples for this plugin.

`uv run pytest` only runs the library's own test suite because `pyproject.toml` sets `testpaths = ["tests"]`.
To run sample applications, target `examples/` explicitly.

## Common Assumptions

These examples assume you have a real device available.

- The baseline verified target is `esp32:esp32:esp32`
- Use `--profile` explicitly when selecting a target
- If you do not want to pass `--profile`, the sample should define `default_profile` in `sketch.yaml`
- Relying on single-profile auto-selection is supported, but not recommended for regular examples

Common example command:

```bash
uv run pytest examples/01_basic --port /dev/ttyUSB0
```

Select another profile explicitly when needed:

```bash
uv run pytest examples/01_basic --profile uno --port /dev/ttyACM0
```

Sample-specific requirements are documented in each sample's own `README.md`.

## Profile Selection

The plugin resolves profiles in this order:

1. `--profile`
2. `default_profile` in `sketch.yaml`
3. Automatic selection when there is exactly one profile
4. Error when multiple profiles exist and no default is defined

The examples in this repository are written with the following convention:

- Prefer `--profile` when running commands explicitly
- If a sample is intended to work without `--profile`, define `default_profile`
- Avoid examples that depend only on single-profile auto-selection

## Execution

Run samples one by one as the default workflow.

Add `-s` when you want to observe the device logs directly during the run.
This is especially useful for examples where the meaning comes from comparing printed values across runs.

Run the whole examples tree only when you want to verify all samples.

```bash
uv run pytest examples/
```

## Basic Features

`--run-mode` controls which stages are executed:

- `--run-mode=all`
  - compile, upload, and test
- `--run-mode=build`
  - compile only
- `--run-mode=test`
  - skip compile, reuse the existing build output, upload, and test

Port resolution uses this priority:

1. `--flash-port`
2. `--port`
3. `TEST_SERIAL_PORT_<PROFILE>`
4. `TEST_SERIAL_PORT`

Use verbosity when you need to inspect what the plugin is doing:

- `-v`
  - shows the `arduino-cli compile` and `arduino-cli upload` commands
- `-vv`
  - also shows resolved details such as `sketch_dir`, `build_path`, `profile`, and `port`

The directories are numbered in the recommended reading and verification order.

- `01_basic`
  - Minimal hello-world example
  - Verified with `esp32` as the default profile
  - Also documents port resolution from `TEST_SERIAL_PORT` and `TEST_SERIAL_PORT_<PROFILE>`
- `02_env_define`
  - Compile-time defines from environment variables
  - Uses Wi-Fi to demonstrate a feature that `uno` should skip
- `03_dut_input`
  - Runtime input sent over serial through `dut.write(...)`
  - Works on both `esp32` and `uno`
- `04_nvs_persistent`
  - ESP32 `Preferences` / NVS data remains across runs by default
  - `uno` is skipped because this example is specifically about ESP32 persistence
- `05_erase_flash`
  - `EraseFlash=all` resets ESP32 persistent data before upload
  - Pairs with `04_nvs_persistent` to show the difference
- `06_arduino_library_project`
  - Practical Arduino library project layout with `tests/` as the `uv` root
  - Includes shell and batch helper scripts for a practical test workspace

## Layout

Each sample directory is one test app.

```text
examples/
  01_basic/
    README.md
    basic/
      sketch.yaml
      basic.ino
      test_basic.py
  02_env_define/
    README.md
    wifi_env_define/
      sketch.yaml
      wifi_env_define.ino
      build_config.toml
      test_env_define.py
  03_dut_input/
    README.md
    serial_dut_input/
      sketch.yaml
      serial_dut_input.ino
      test_dut_input.py
  04_nvs_persistent/
    README.md
    nvs_persistent/
      sketch.yaml
      nvs_persistent.ino
      test_nvs_persistent.py
  05_erase_flash/
    README.md
    nvs_erase_flash/
      sketch.yaml
      nvs_erase_flash.ino
      test_nvs_erase_flash.py
  06_arduino_library_project/
    README.md
    demo_add_library/
      library.properties
      src/
      tests/
```

This plugin treats the directory containing the selected test file as the sketch directory.

## Notes

- `examples/pytest.ini` is a local config to suppress a warning emitted by `pytest-embedded`
- `02_env_define` requires `TEST_WIFI_SSID` and `TEST_WIFI_PASSWORD`
- `-s` is useful when you want to see serial output such as `BOOT_COUNT` while the test is running
