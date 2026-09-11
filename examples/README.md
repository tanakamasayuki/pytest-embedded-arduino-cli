# examples

[日本語版 (Japanese)](README.ja.md)

`examples/` contains runnable reference implementations organized by purpose. If you are adding the plugin to your own project for the first time, start with [Your First Test](../FIRST_TEST.md).

The numbers are not a strict difficulty scale. Select the example for the feature you need instead of treating this as a course that must be run from `01` onward.

## Where to start

### You have a physical board

Run `01_basic` first to check compile, upload, and a serial round trip.

```bash
uv run pytest examples/01_basic --profile=uno --port=/dev/ttyACM0
uv run pytest examples/01_basic --profile=esp32 --port=/dev/ttyUSB0
```

Then try `03_dut_input` for the usual request-and-response test shape.

### You do not have a board

Start with `09_host_arduino_core`. It needs a host core and C++ toolchain, but no serial device.

```bash
uv run pytest examples/09_host_arduino_core --profile=host
```

A host core checks logic and serial protocols. Use hardware for peripherals, interrupts, real-time timing, Flash/NVS, and board-specific APIs.

### You want a realistic project layout

`07_arduino_library_project` and `08_arduino_ide_project` are independent workspaces. Change into their respective `tests/` directories before running them.

## Examples by purpose

| Example | Requirements | Subject | Related guide |
| --- | --- | --- | --- |
| [`01_basic`](01_basic/README.md) | One board | Minimal compile, upload, and serial round trip | [Your First Test](../FIRST_TEST.md) |
| [`02_env_define`](02_env_define/README.md) | ESP32, Wi-Fi settings | Environment values as compile-time defines | [Advanced: configuration precedence](../TESTING_ADVANCED.md#configuration-precedence-and-env) |
| [`03_dut_input`](03_dut_input/README.md) | One board | Runtime input with `dut.write()` | [Basics: how it works](../TESTING_BASICS.md#how-it-works) |
| [`04_unity_basic`](04_unity_basic/README.md) | ESP32 | Device-side assertions | [Basics: pass/fail location](../TESTING_BASICS.md#there-are-two-places-to-decide-pass-or-fail) |
| [`05_nvs_persistent`](05_nvs_persistent/README.md) | ESP32 | NVS surviving upload | [Basics: session, module, test](../TESTING_BASICS.md#session-module-test) |
| [`06_erase_flash`](06_erase_flash/README.md) | ESP32 | Full Flash erase before upload | [Basics: session, module, test](../TESTING_BASICS.md#session-module-test) |
| [`07_arduino_library_project`](07_arduino_library_project/README.md) | One board | Arduino library workspace | [Basics: directory layout](../TESTING_BASICS.md#directory-layout) |
| [`08_arduino_ide_project`](08_arduino_ide_project/README.md) | One board | Arduino IDE project workspace | [Basics: directory layout](../TESTING_BASICS.md#directory-layout) |
| [`09_host_arduino_core`](09_host_arduino_core/README.md) | Host core, C++ toolchain | Running a sketch without a board | [Basics: zero boards](../TESTING_BASICS.md#zero-boards-run-on-a-host-core) |
| [`10_build_flags`](10_build_flags/README.md) | Host core, C++ toolchain | Valueless compile-time flags | [Advanced: compile-time defines](../TESTING_ADVANCED.md#compile-time-defines) |
| [`11_ardutest`](11_ardutest/README.md) | Host core or board | ArduTest fixture | [README: ArduTest](../README.md#ardutest-fixture) |
| [`12_peer_host_core`](12_peer_host_core/README.md) | Host core, C++ toolchain | Primary and peer layout | [Basics: two boards](../TESTING_BASICS.md#two-boards-tests-that-need-a-partner) |

`05`/`06` and `02`/`03` form pairs: persistent versus erased state, and compile-time versus runtime values.

## Common prerequisites

- `arduino-cli` is on `PATH`
- The selected profile declares and pins its platform version in `sketch.yaml`, and Arduino CLI can resolve it from its indexes; examples never depend on a preinstalled unversioned core
- Hardware examples have a serial port accessible from the host

Refresh the indexes when a version cannot be found:

```bash
arduino-cli core update-index
arduino-cli lib update-index
```

Set `platform_index_url` in a profile when its core needs an additional Board Manager URL. Projects distributing binaries should pin the production build version; projects distributing source should generally track newer core releases and test each update.

Bare `uv run pytest` at the repository root runs only the plugin's own tests. Always pass an example path explicitly.

## Profiles and ports

The primary profile is resolved from `--profile`, `default_profile`, then automatic selection of a single profile. Multiple remaining profiles are an error. Name the profile in example commands to make the selected board explicit.

The port is resolved from `--flash-port`, `--port`, `TEST_SERIAL_PORT_<PROFILE>`, `TEST_SERIAL_PORT`, then a `socket://...` value in `sketch.yaml`. Write physical ports with `=`, such as `--port=/dev/ttyUSB0`, to avoid ambiguity with pytest path parsing. Repeated values can go in `.env`.

## Running examples

Run examples one at a time. Add `-s` for device logs, `-v` for assembled commands, and `-vv` for resolved paths, profiles, and ports.

- `--run-mode=all`: compile, upload, and test; the default
- `--run-mode=build`: compile only; test items are reported as skipped
- `--run-mode=test`: upload and test an existing build for the same profile

Examples require different hardware and environment values, so running the entire tree is not the normal onboarding path. Name compatible examples explicitly when compiling a group.

## Maintaining examples

- Keep each example focused on one subject.
- Prefer a handshake pytest can query over one startup-only message.
- State the command, required board/core, and expected result in each README.
- Link new features from this table and the relevant guide section in both directions.
- Keep one `.ino` per test directory and move supporting code to `.h` / `.cpp`.
