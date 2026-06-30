# pytest-embedded-arduino-cli Specification

[日本語版 (Japanese)](SPEC.ja.md)

## 1. Purpose of This Document

This document is a specification for organizing the requirements of the new Python package / pytest plugin `pytest-embedded-arduino-cli`.

The purpose of this plugin is to provide Arduino build / upload based on `arduino-cli`, while building on top of the core / serial / expect features of `pytest-embedded`.

It does not aim primarily at compatibility with the existing `pytest-embedded-arduino`. Instead, it distances itself from ESP-specific implementations and prioritizes a structure that can easily expand to Arduino-compatible boards other than ESP32 in the future.

## 2. Background

- The existing `pytest-embedded` allows generic reuse of core features such as DUT, serial, and expect.
- On the other hand, `pytest-embedded-arduino`, even though it targets Arduino, leans toward ESP-based implementations.
- In particular, since the serial layer is built on `EspSerial`, it tends to become a design constraint when expanding to boards other than ESP32.
- The direction of replacing build with `arduino-cli compile` and upload with `arduino-cli upload` is already in sight.
- Therefore, we design a new plugin that carves out only the Arduino build / upload as an independent responsibility, while leveraging the generic features of `pytest-embedded` for DUT connection and expect during test execution.

## 3. Product Overview

- Package name: `pytest-embedded-arduino-cli`
- Description: `A pytest plugin to test Arduino projects using pytest-embedded and arduino-cli`
- Type:
  - Python package
  - pytest plugin
- Intended users:
  - Users who want to build / flash with the Arduino CLI
  - Users who want to perform real-board tests using the serial / expect features of `pytest-embedded`
  - Users who want to expand to multiple Arduino-compatible boards in the future, rather than being ESP32-only

## 4. Design Principles

### 4.1 Core Policy

- Build on top of `pytest-embedded`
- Do not depend on `pytest-embedded-arduino`
- Build with `arduino-cli compile`
- Upload with `arduino-cli upload`
- Use the generic DUT / serial / expect of `pytest-embedded` for the test runtime
- Do not depend on ESP-specific classes or ESP-specific services
- Build on a generic serial base as much as possible
- Prioritize simple, maintainable separation of responsibilities over reproducing compatibility

### 4.2 Separation of Responsibilities

This plugin clearly separates at least the following responsibilities.

- plugin layer:
  - Entry point as a pytest plugin
  - pytest option registration
  - Providing fixtures
  - Defining connection points with `pytest-embedded`
- app / builder layer:
  - Assembling `arduino-cli compile` arguments
  - Resolving the build directory
  - Organizing sketch.yaml / profile / build property
- flasher layer:
  - Assembling `arduino-cli upload` arguments
  - Organizing upload port / profile / input artifact
- serial connection layer:
  - A thin adapter wrapping generic serial as needed
  - Avoid increasing custom implementations too much, and prioritize leveraging the existing serial foundation of `pytest-embedded`

## 5. Scope

### 5.1 Included in This Specification

- A publishable, independent Python package structure
- `src` layout
- Definition of a pytest plugin entry point
- A build mechanism that calls `arduino-cli compile`
- An upload mechanism that calls `arduino-cli upload`
- Device locking that prevents concurrent upload / test use of the same physical serial device
- Adding pytest options
- DUT connection design premised on the core / serial / expect of `pytest-embedded`
- Unit tests that verify command generation and option interpretation
- Minimal integration tests that confirm plugin loading
- README and examples
- Design of the `arduino_test` fixture that integrates with the Arduino-side test library `ArduTest`

### 5.2 Not Included in This Specification

- Full compatibility with `pytest-embedded-arduino`
- ESP-specific features
  - erase-all
  - board interpretation premised on a chip target
  - ESP ROM / monitor specific behavior
- Complex board-specific dedicated upload strategies
- Advanced `arduino-cli board list` integration or automatic port resolution
- Optimization of automatic artifact discovery per board definition
- Device farm features beyond same-device exclusion

### 5.3 Related Specifications

The details of the communication protocol, initial synchronization, execution control, and artifact collection between `ArduTest` and the `arduino_test` fixture are managed in [`ARDUTEST_PROTOCOL_SPEC.md`](ARDUTEST_PROTOCOL_SPEC.md).

The pytest-side details such as the public API of the `arduino_test` fixture, configuration resolution, reflection into pytest results, and artifact saving are managed in [`ARDUTEST_PYTEST_SPEC.md`](ARDUTEST_PYTEST_SPEC.md).

## 6. Intended Use Cases

### 6.1 Basic Use Case

When running pytest, the user should be able to do the following.

1. Build an Arduino sketch with `arduino-cli compile`
2. Flash the build artifact with `arduino-cli upload`
3. Connect to the DUT via a serial port
4. Test using the standard interface of `pytest-embedded`, such as `dut.expect(...)`

For board cores that run the sketch on the host machine, it should be possible to connect to the DUT via a TCP/IP socket instead of a physical serial port.
Even in this case, the Python test side should be able to use `dut.expect(...)` and `dut.write(...)` to perform simple tests in a form close to real-board serial.

### 6.2 Execution Modes

At least the following modes are assumed.

- build + test
- build only
- test only

In the case of `test only`, the existing build artifact is reused, the upload is performed, and then the test is executed.

### 6.3 Rules for Resolving Test Targets

The intended usage assumes the Arduino sketch and the pytest test are placed in the same directory.

- `.py` and `.ino` are placed in the same directory
- When pytest is run on a directory basis, the test targets under it are handled in order
- When a specific `.py` is passed to pytest, the `.ino` placed in the directory of that `.py` is the target
- The compile conditions of the sketch are resolved from `sketch.yaml`

We do not introduce the premise of explicitly specifying the sketch location with a CLI option.

Only the profiles listed in the `sketch.yaml` in the same directory are considered the profiles that the sketch supports.
If an unsupported profile is specified with `--profile`, that sketch is treated as a skip target before build.

### 6.4 Multi-Board Tests Using Peer DUTs

For tests that use multiple DUTs, a `peer_<name>` directory may be placed directly under the normal test/sketch directory.

Example:

```text
host_smoke/
  host_smoke.ino
  sketch.yaml
  test_host_smoke.py
  peer_echo/
    peer_echo.ino
    sketch.yaml
  peer_bridge/
    peer_bridge.ino
    sketch.yaml
```

- The sketch directly under the test/sketch directory is the primary DUT and is handled with the `dut` fixture as before
- The `peer_<name>` directory is a peer DUT and can be referenced with `peers["<name>"]`
- Each `peer_*` directory is treated as an independent Arduino sketch directory
- Each peer DUT has its own `.ino` and `sketch.yaml`
- `sketch.yaml` is treated as the standard format of the Arduino CLI, and no custom items for peer DUTs are added
- No additional configuration files for peer DUTs are introduced

Test example:

```python
def test_round_trip(dut, peers):
    echo = peers["echo"]

    dut.expect_exact("main ready")
    echo.expect_exact("echo ready")
```

In principle, peer DUTs are uploaded and connected only in tests that request the `peers` fixture.
If `peer_*` directories exist, their sketches may be compiled before primary upload so all compile work finishes before any upload begins.
Once the `peers` fixture is requested, the test is considered to use peer DUTs, and whether `peers["<name>"]` is actually referenced within the test function is not used as an activation condition.
This is to allow tests where the peer DUT operates autonomously and verification is performed only by observation from the primary DUT side.

When flashing the same sketch to multiple boards, separate the peer directories, such as `peer_sensor1` and `peer_sensor2`.
Prioritizing the policy of not increasing configuration files, the initial specification does not have an alias setting for assigning the same sketch path to multiple peers.

## 7. Dependencies

### 7.1 Runtime Dependencies

At least the following are included as regular dependencies.

- `pytest`
- `pytest-embedded`

`pytest-embedded` is a runtime dependency, not a dev dependency.

### 7.2 External Command Dependency

- `arduino-cli` must be installed in the execution environment

The installation of `arduino-cli` itself and the introduction of the board core are not included in the responsibilities of this plugin.

## 8. Package Structure Requirements

At a minimum, it has a structure like the following.

```text
pyproject.toml
README.md
SPEC.ja.md
src/
  pytest_embedded_arduino_cli/
    __init__.py
    plugin.py
    app.py
    flasher.py
    serial.py        # only when necessary
tests/
examples/
```

Adding auxiliary modules is allowed, but do not increase responsibilities too much.

## 9. pytest plugin Requirements

### 9.1 entry point

Define the pytest plugin entry point in `pyproject.toml`.

Expected example:

- group: `pytest11`
- name: `embedded-arduino-cli`
- value: `pytest_embedded_arduino_cli.plugin`

### 9.2 Responsibilities of the plugin

`plugin.py` is responsible for the following.

- Registering pytest options
- Providing necessary fixtures on a session / module / function basis
- Execution control of build / upload
- Exposing fixtures to integrate with `pytest-embedded`
- Delegating CLI execution and argument construction to other modules so that services can be separated easily in the future

### 9.3 Non-Responsibilities of the plugin

Do not give `plugin.py` itself a long command-assembly logic.

## 10. App / Builder Requirements

### 10.1 Purpose

Organize the information needed to run `arduino-cli compile` and provide a stable command generation API.

### 10.2 Main Responsibilities

- Resolving the sketch directory based on the test file location
- Resolving the build path
- Holding the compile conditions based on `sketch.yaml` and profile
- Injecting compile-time defines / flags based on `build_config.toml`
- Generating the compile command
- A thin wrapper for subprocess execution
- Separating command generation and execution to make testing easier

### 10.3 Inputs Handled

- build path
- profile
- board options / build properties
- extra compile args
- whether it is a clean build

The main inputs are as follows.

- The location of the test file
- `sketch.yaml`
- `--profile`
- Environment variables as needed

### 10.4 Handling the Profile Support Range

The profiles written in `sketch.yaml` are the list of profiles that the sketch supports.

The expected behavior is as follows.

1. If `--profile` is specified and its value exists in `sketch.yaml`, use that profile
2. If `--profile` is specified and its value does not exist in `sketch.yaml`, skip that sketch
3. If `--profile` is not specified and `default_profile` is defined, use it
4. If `--profile` is not specified and there is only one profile, automatically select it
5. If `--profile` is not specified, there are multiple profiles, and there is no `default_profile`, treat it as a configuration error and raise an error

With this design, the correct configuration is to write only the supported profiles in `sketch.yaml`.
A configuration that forcibly lists unsupported profiles and calls `pytest.skip()` on the Python side is not recommended.

### 10.5 `build_config.toml`

A `build_config.toml` may be placed in the sketch directory as needed.

Intended uses:

- Wi-Fi SSID / password
- API endpoint
- Test flags

This file is used to define the correspondence between environment variable names and compile-time define names, as well as compile-time flags without values.

Expected example:

```toml
[defines]
TEST_WIFI_SSID = "WIFI_SSID"
TEST_WIFI_PASSWORD = "WIFI_PASSWORD"

[flags]
PYTEST_BUILD = true
ENABLE_TEST_HOOKS = true
```

`[defines]` treats the left side as the environment variable name and the right side as the C/C++ define name.
The plugin reads the specified environment variable and converts it to the form `-D<define_name>="<environment_variable_value>"`, passing it through `arduino-cli compile --build-property <property>=...`.
Even if the environment variable is not set, an empty string is passed to that define.

`[flags]` is used to explicitly specify defines without values.
It treats the left side as the C/C++ macro name and the right side as a boolean, converting only the items that are `true` to `-D<macro_name>`.
Items that are `false` are not emitted.
Non-boolean values are treated as a configuration error and raise an error.

Test flags like `PYTEST_BUILD` are not automatically added by the plugin.
To avoid implicitly testing something different from the production code path, the project that needs them explicitly specifies them in the `[flags]` of `build_config.toml`.

#### Injection property selection

Because `--build-property X=Y` *replaces* the property rather than appending, the target property must be one the platform leaves empty (otherwise platform-defined flags would be discarded). On host / AVR boards `build.extra_flags` is often empty, but on ESP32 it is platform-populated, and some ESP32 board options also populate `build.defines`.

The plugin therefore selects the injection property automatically, only when there are defines/flags to inject and only at compile time (`--run-mode=all` / `build`):

1. It probes the resolved (expanded) properties with `arduino-cli compile --show-properties` for the same sketch / profile that will be built.
2. It picks the first candidate group that exists and is empty, in this order: `build.extra_flags`, `build.defines`, then both `compiler.cpp.extra_flags` and `compiler.c.extra_flags`, then `compiler.cpp.extra_flags` alone. This keeps broad properties when they are safe, and falls back to C/C++ compile flags when ESP32 board settings occupy the build-level properties.
3. If no candidate group is empty, it raises a clear error (showing the non-empty values) before compiling, instead of letting a clobbered build fail cryptically.

The probe is skipped entirely when there are no defines/flags, when a manual override is set (below), and in `--run-mode=test`.

A project can override the property explicitly in `build_config.toml`, which also skips the probe (about one second faster):

```toml
build_property = "build.defines"        # top-level default for all profiles

[profiles.esp32]
build_property = "build.defines"        # per-profile override (resolved profile name)
```

Precedence: per-profile `[profiles.<name>].build_property` > top-level `build_property` > auto-detection.

Automatic loading of `.env` files is not included in this specification.

### 10.6 Command Generation Policy

- Command generation is a near-pure function or a dataclass-based API
- Actual command execution is separated into another method or another function
- In tests, focus on verifying the command array rather than subprocess execution

## 11. Flasher Requirements

### 11.1 Purpose

Organize the information needed to run `arduino-cli upload` and separate the upload responsibility from build.

### 11.2 Main Responsibilities

- Resolving the build path of the upload target
- Holding upload conditions such as port / protocol / profile
- Generating the upload command
- A thin wrapper for subprocess execution

### 11.3 Inputs Handled

- build path
- port
- profile
- extra upload args

### 11.4 Policy

- Does not hold the responsibility of generating the build artifact
- Concentrates only on upload
- Does not introduce board-specific optimization at the initial stage
- A runtime connection target such as `--port=socket://...` is not passed to `arduino-cli upload --port`
- If runtime connection target completion is needed after upload, it is handled in the DUT / Serial integration layer

## 12. Device Lock Requirements

### 12.1 Purpose

When multiple pytest processes are run across one or more projects, the plugin should prevent two processes from uploading to or testing with the same physical DUT at the same time.

The lock is for physical device use, not for compilation. Build steps must remain able to run before waiting for the device lock.

### 12.2 Lock Target

The default lock key is the resolved physical serial port.

- For the primary DUT, use the resolved upload / runtime serial port, following the normal `--flash-port`, `--port`, and environment variable priority.
- For peer DUTs, use each peer's resolved runtime / upload serial port.
- Profile name is not the default lock key because two projects can use the same profile name for different devices, and two different profiles can still address the same physical device.
- `socket://...` targets are not locked by default because they normally represent host-process or TCP/IP DUTs rather than a shared physical serial device.

If multiple peer DUTs are used in one test, all physical serial lock keys required by those peer DUTs are collected when the `peers` fixture is requested. Duplicate physical serial keys in the same peer set are treated as a configuration error. A peer lock key that duplicates the already-held primary DUT lock key is also treated as a configuration error.

### 12.3 Lock Timing and Lifetime

The plugin acquires device locks after compilation has completed and immediately before the first upload that needs the device.

The lock is held until the module-level DUT use is finished, including upload, runtime serial connection, test execution, and teardown of primary / peer DUTs.
Releasing the lock immediately after upload is not sufficient because another pytest process could upload new firmware while the first test is still interacting with the DUT.

`--run-mode=build` does not acquire device locks.
`--run-mode=all` and `--run-mode=test` acquire locks when a lockable physical serial target is resolved.

For the peer DUT set, locks are acquired in a deterministic sorted order by lock key to avoid deadlocks across processes. The primary DUT lock is acquired earlier, before primary upload, because peer DUTs are only prepared for tests that request the `peers` fixture.

### 12.4 Lock Storage and Stale Locks

Device locks are stored in a user-level runtime or cache directory, not under the project directory, so separate projects on the same machine share the same exclusion domain.
The default directory is resolved as follows:

1. On Windows, use `%LOCALAPPDATA%\pytest-embedded-arduino-cli\locks` when `LOCALAPPDATA` is set.
2. On Windows, fall back to `%APPDATA%\pytest-embedded-arduino-cli\locks` when `APPDATA` is set.
3. On Windows, fall back to `~/AppData/Local/pytest-embedded-arduino-cli/locks`.
4. On non-Windows platforms, use `$XDG_RUNTIME_DIR/pytest-embedded-arduino-cli/locks` when `XDG_RUNTIME_DIR` is set.
5. On non-Windows platforms, fall back to `$XDG_CACHE_HOME/pytest-embedded-arduino-cli/locks` when `XDG_CACHE_HOME` is set.
6. On non-Windows platforms, fall back to `~/.cache/pytest-embedded-arduino-cli/locks`.

Lock file names should be based on a normalized or hashed lock key, not on raw path text.

The presence of a lock file alone must not mean the device is busy.
The implementation must rely on an operating-system file lock, such as one provided by `portalocker`, so process termination releases the actual lock when the OS closes the file descriptor.
The lock file may remain after a forced termination and is treated as reusable metadata.

While holding the lock, the plugin may write diagnostic metadata to the lock file, such as:

- process id
- hostname
- lock key
- port
- profile
- sketch directory
- start time

This metadata is for logging and timeout diagnostics only, not for the authoritative exclusion check.

### 12.5 Lock Options

The following pytest options control device locking.

- `--device-lock=auto|off|required`
- `--device-lock-timeout=SECONDS`
- `--device-lock-dir=PATH`
- `--device-lock-key=KEY`

The default is `--device-lock=auto`.

Mode meanings:

- `auto`: acquire a lock when a physical serial lock key can be resolved; continue without a lock for non-lockable targets such as default socket URLs.
- `off`: do not acquire device locks.
- `required`: require a lock key for upload/test runs; fail with a usage/configuration error if no lock key can be resolved.

`--device-lock-timeout` controls how long to wait for an already-held lock before failing.
On timeout, the error message should include the requested key and any readable diagnostic metadata from the existing lock file.

`--device-lock-dir` overrides the default user runtime/cache lock directory.
It is intended for CI isolation or shared lab machines with explicit coordination requirements.

`--device-lock-key` overrides automatic key resolution for the primary DUT.
It is intended for unusual environments where the serial port string is not a stable physical-device identity.
Peer DUTs continue to use their own resolved port keys unless a future peer-specific override is added.

## 13. DUT / Serial Integration Requirements

### 13.1 Basic Policy

- DUT, serial, and expect leverage the existing generic features of `pytest-embedded`
- Do not depend on `EspSerial` or ESP-specific classes

### 13.2 Design Intent

- Separate build / upload from the test runtime
- Keep the test runtime side as board-independent as possible
- Make it possible in the future to carve out per-board-family differences into an upload strategy or service layer as needed

### 13.3 Goals

- Testing is possible on boards that can be connected with generic serial
- Basic `expect`-based tests using the standard DUT of `pytest-embedded` are established
- A different serial port per profile can be resolved from environment variables
- On board cores that run on the host machine, the DUT can be connected via TCP/IP using pyserial's `socket://` URL

### 13.4 Socket Connection of the host Arduino core

On board cores that run the Arduino sketch on the host machine, a socket URL without a port number, such as `--port=socket://localhost`, may be specified.

The flow in this case:

1. Build the host executable with `arduino-cli compile`
2. Start the host executable with `arduino-cli upload`
3. Search for `*.host-arduino.json` under the build output directory
4. Read the `port` from the JSON
5. Complete the runtime connection target as `socket://localhost:<port>`
6. Connect to the DUT as a socket URL of `pytest-embedded-serial` / pyserial

Expected schema of the host-arduino information file:

```json
{
  "pid": 21228,
  "port": 56789
}
```

`port` must be an integer between 1 and 65535 inclusive.
`pid` is not mandatorily used in the initial implementation, but it can be used for future cleanup or diagnostic purposes.

If a port number is specified down to `socket://localhost:56789`, completion via JSON search is not performed, and that URL is used directly as the runtime connection target.

If `--flash-port` is specified, it follows the existing port priority order and is prioritized as the upload port.
For socket execution of the host Arduino core, the assumed usage is normally not to use `--flash-port` but to use `--port=socket://...`.

Even if `HOST_ARDUINO_PORT=...` appears in the standard output of the upload, the plugin does not require stdout capture.
In order not to change the existing upload display behavior, port resolution prioritizes the `*.host-arduino.json` in the build output directory.

Host execution is for simple verification of pure logic or serial protocol, and is not a substitute for real-board testing.
Results may vary due to the OS, the toolchain version such as gcc, and implementation differences in the host core's `Serial` class.
Peripherals, timing, interrupts, Flash/NVS, and board-specific APIs are verified on the real board.
In addition, it is recommended to separately perform a build test with the board profile used in production.

### 13.5 Division of Responsibilities for skip

This plugin should be able to determine skip due to unsupported profiles before build.

- If a profile not present in `sketch.yaml` is specified, skip that sketch before compile / upload
- This skip does not depend on `pytest.skip()` inside the test function

On the other hand, cases where execution becomes impossible due to real-board state or external conditions even with the same profile may use `pytest.skip()` on the test side.
For example, runtime conditions such as Wi-Fi connection conditions or external service conditions may be handled on the Python test side.

### 13.6 Profile Resolution of Peer DUTs

The profile of a peer DUT is resolved based on each `peer_<name>/sketch.yaml`.

The profile resolution order of a peer DUT is as follows.

1. `--peer-profile <name>:<profile>`
2. `default_profile` of `peer_<name>/sketch.yaml`
3. If it cannot be determined, skip the test that requires that peer DUT

`--profile` is exclusive to the primary DUT and is not used for peer DUT profile resolution.
For peer DUTs, even if there is only one profile, it is not automatically selected.
This is to avoid unintentionally running heavy multi-board tests.

If the profile specified with `--peer-profile` does not exist in the peer DUT's `sketch.yaml`, skip the test that requires that peer DUT.

Since peer DUTs are often used in heavy multi-board tests, do not define `default_profile` for peer sketches that you do not want to run without specification.
In this case, if `--peer-profile` is not specified, tests that use the `peers` fixture are skipped.

### 13.7 Port Resolution of Peer DUTs

`--port` and `--flash-port` are exclusive to the primary DUT.
The port of a peer DUT is resolved based on the peer name, and does not implicitly reuse the primary DUT's port specification.

The runtime port resolution order of a peer DUT is as follows.

1. `--peer-port <name>:<port>`
2. `TEST_SERIAL_PORT_PEER_<NAME>_<PROFILE>`
3. `TEST_SERIAL_PORT_PEER_<NAME>`
4. When `profiles.<profile>.port` of `peer_<name>/sketch.yaml` is a `socket://...` URL
5. If it cannot be resolved, skip the test that requires that peer DUT

`<NAME>` and `<PROFILE>` are in a form that is uppercased and has `-` replaced with `_`.
For example, the `host` profile of `peer_echo` refers to `TEST_SERIAL_PORT_PEER_ECHO_HOST`.

In the upload port resolution of a peer DUT, if the runtime port is a `socket://...` URL, it is not passed to `arduino-cli upload --port`.
This is to treat the socket URL as the runtime connection target, just like the primary DUT.

Peer DUTs can also use the host Arduino core's socket URL without a port number.
A URL such as `socket://localhost` is completed by reading the `port` from the `*.host-arduino.json` under that peer DUT's build output directory after that peer DUT's upload.

### 13.8 Build / Upload / Connect of Peer DUTs

The build path of a peer DUT is `<peer_dir>/build/<profile or default>` under each peer sketch directory.
The build path of the primary DUT and the build path of the peer DUT are separated.

When peer directories are present, the plugin compiles peer DUTs before primary upload when build is enabled.
When the `peers` fixture is requested, the plugin performs upload / runtime port completion / connection for the detected peer DUTs.
`peers["<name>"]` is a mapping API for referencing connected peer DUTs, and the specification is not to lazily start only the referenced peer.

- `--run-mode=all`: Build the peer DUT, upload, and then run the test
- `--run-mode=build`: Build the peer DUT and skip test execution. In this case, the peer port is not needed
- `--run-mode=test`: Use the existing build artifact to upload the peer DUT and then run the test

The order of upload / connect is as follows.

1. Build the primary DUT
2. Build detected peer DUTs in name order
3. Upload the primary DUT
4. When the `peers` fixture is requested, upload the detected peer DUTs in name order
5. Perform runtime port completion of the peer DUTs
6. Connect to the peer DUTs and provide them as `peers["<name>"]`
7. Connect to the primary DUT through the normal processing of pytest-embedded and provide it as `dut`

In this order, the Python side may miss the startup message that the real-board DUT outputs only briefly immediately after upload.
In environments where the output is retained until the socket connection, such as the host Arduino core, this is unlikely to be a problem, but for general real-board serial, it is recommended to prepare sufficient waiting, retransmission, or a handshake on the sketch side that waits for input from the Python side.
Especially for peer DUTs, since all detected peers are started when the `peers` fixture is requested, tests that depend on the startup order between DUTs synchronize via the sketch-side protocol.

Structural defects of peer DUTs are treated as configuration errors.
For example, if there is no `.ino`, there are multiple `.ino` files, or the `sketch.yaml` is broken, it is treated as an error.
On the other hand, if the execution conditions are not met, such as unsupported profile, undetermined profile, or unresolved port, it is treated as skip.

## 14. pytest option Requirements

At least the following categories of options are targeted.

### 14.1 Execution Mode

- Whether to build
- Whether to upload
- Whether to run the test

Example:

- `--run-mode=all|build|test`

The meanings are as follows.

- `all`: build → upload → test
- `build`: build only
- `test`: use the existing build artifact to upload → test

### 14.2 Arduino CLI compile Related

- profile

The compile-related option specific to this plugin is only `--profile`.
The build path is fixed to `<sketch_dir>/build/<profile or default>`, and the MVP does not have an override.

Before build execution, determine whether the profile is supported, and do not compile sketches with unsupported profiles.

### 14.3 Arduino CLI upload Related

No upload-related options specific to this plugin are added.
For the port specification needed for upload, use the standard `--flash-port` or `--port` of `pytest-embedded`.
However, since `--port=socket://...` represents the runtime connection target, it is not passed to `arduino-cli upload --port`.

### 14.4 Peer DUT Related

To individually specify peer DUTs, the following options are added.

- `--peer-profile <name>:<profile>`
- `--peer-port <name>:<port>`

Both can be specified multiple times.

Example:

```bash
pytest tests/foo \
  --peer-profile echo:host \
  --peer-profile bridge:esp32 \
  --peer-port echo:socket://localhost \
  --peer-port bridge:/dev/ttyUSB1
```

The values of `--peer-profile` and `--peer-port` are in `<peer-name>:<value>` format.
Multiple specification separated by `,` is not adopted; to specify multiple peers, write the option multiple times.

A value that does not contain `:` is treated as an error.
If the same peer name is specified multiple times in the same option, it is treated as an error.
If a nonexistent peer name is specified, it is also treated as an error.

`--peer-profile` only affects the profile resolution of the corresponding peer DUT.
`--peer-port` only affects the runtime port / upload port resolution of the corresponding peer DUT.
The behavior of the primary DUT's `--profile`, `--port`, and `--flash-port` is maintained as before.

### 14.5 serial / DUT Related

- Leverage the standard options of `pytest-embedded`
- Bridge on the plugin side as needed
- Assume at least `--port`, `--flash-port`, `--baud`, and `--embedded-services`

The serial port should be resolvable in the following priority order.

1. `--flash-port`
2. `--port`
3. Environment variable per profile
4. Common environment variable

The environment variable name per profile is in a form that normalizes the profile name, such as `TEST_SERIAL_PORT_ESP32S3`.
The common environment variable is `TEST_SERIAL_PORT`.

If a socket URL such as `socket://localhost` is specified in `--port` or an environment variable, it is treated as the runtime connection target.
A socket URL without a port number is completed by reading the `port` from the `*.host-arduino.json` in the build output directory after upload.
A socket URL with a port number is used directly without completion.

### 14.6 Device Lock Related

The plugin adds device-lock options to protect shared physical DUTs across concurrent pytest processes.

- `--device-lock=auto|off|required`
- `--device-lock-timeout=SECONDS`
- `--device-lock-dir=PATH`
- `--device-lock-key=KEY`

The default is `auto`.
This means normal real-board upload/test runs are protected without additional configuration, while build-only and default socket-based host runs do not wait for a physical-device lock.

### 14.7 pytest Standard Verbosity Integration

- No additional dedicated verbose option is provided
- Vary the amount of build / upload log output according to pytest's standard `-v` / `-vv`
- With `-v`, display the executed commands of `arduino-cli compile` / `arduino-cli upload`
- With `-vv`, in addition to the above, also display the execution context such as `cwd`, `sketch_dir`, `build_path`, `profile`, and `port`

When a pre-build skip occurs, it is desirable to have output at `-v` or higher that makes it clear that the skip was due to an unsupported profile.
For peer DUT build / upload as well, include information in the `-v` / `-vv` logs that identifies the peer name.

### 14.8 Option Design Policy

- Prioritize the terminology of `arduino-cli` for naming
- Do not bring ESP-specific terminology into option names
- Use names that are unlikely to conflict with existing pytest-embedded options
- Make the responsibility boundaries of build / upload / runtime visible from the option names
- Keep plugin-specific options small and scoped to execution mode, profile selection, peer DUTs, device locking, ArduTest, and local state cache

## 15. Test State Saving Requirements

### 15.1 Purpose and Positioning

For real-board microcontroller tests run with pytest, save the verification state of each test to a local file.

The main purpose is to make it possible, during local development, to check "when it last succeeded" and "what the previous result was".

This feature is treated as a "real-board verification state cache", and the following are out of scope.

- Test reports, long-term history management, CI dashboards, quality gates
- Accumulation of execution history, metrics collection, trend analysis
- Saving artifacts such as build artifacts, logs, serial output, and screenshots
- Automatic deletion of stale entries or rename detection

The state cache is a disposable file that does not affect the test body or build even if reset according to the execution environment.

### 15.2 Basic Policy

- The state is updated only when verification is actually performed on the real board
- The unit of recognition is the pair `(profile_name, nodeid)`
- Splitting into separate files per profile is not included in the initial specification
- state.json is a current state cache and does not retain append-only history
- It does not guarantee an exact match with pytest collection
- It allows stale entries to remain

### 15.3 Save Destination and Structure

#### 15.3.1 Directory Setting

The state save directory can be specified with a CLI option.

- option: `--save-state-dir`
- default: `.pytest-results`
- An absolute path or a relative path (based on the pytest rootdir) can be specified
- It is recommended to keep it out of git management, and adding it to `.gitignore` is recommended

#### 15.3.2 File Structure

- The state is saved to `<save_state_dir>/state.json`
- `<save_state_dir>/` is treated as a directory for local state saving
- A structure that can hold other cache files for future expansion is assumed, but the initial specification has only `state.json`

#### 15.3.3 state.json Structure

```json
{
  "schema_version": 1,
  "updated_at": "2026-05-10T20:00:00+09:00",
  "profiles": {
    "uno": {
      "tests": {
        "tests/test_gpio.py::test_led": {
          "last_result": "passed",
          "last_run_at": "2026-05-10T20:00:00+09:00",
          "last_success_at": "2026-05-10T20:00:00+09:00"
        }
      }
    },
    "esp32": {
      "tests": {
        "tests/test_gpio.py::test_led": {
          "last_result": "failed",
          "last_run_at": "2026-05-10T20:05:00+09:00",
          "last_success_at": "2026-05-09T18:30:00+09:00"
        }
      }
    }
  }
}
```

- Internally, the profile name is managed as the parent key
- Under each profile, the test state keyed by the pytest `nodeid` is saved
- For the profile name, the actual final execution profile name that was used is used as-is
- Even in an execution without profile specification, the internally selected final profile name is used
- Synthetic/default profile names are not used

### 15.4 Saved Content

For each test, save at least the following.

- `last_result`: the last result (`passed`, `failed`, `error`, etc.)
- `last_run_at`: the last execution date/time (ISO8601 format, with time zone)
- `last_success_at`: the last success date/time (ISO8601 format, with time zone)

- Until the first success, `last_success_at` does not need to exist
- An unexecuted test is expressed by the absence of an entry in `state.json`
- The JSON is in a format that is both human-readable and machine-processable

### 15.5 Determining Save Targets

The state is updated only when verification is actually performed on the real board.

The state is not updated in the following cases:

- `build failed`: when compile fails
- `upload failed`: when upload fails
- Failure due to environmental factors: board not found, port open failed, device unavailable, etc.
- `skipped`, `deselected`: when the test was not executed

When the state is updated:

- Only results where the test actually started on the board, such as `pass`/`fail`/`error`, are update targets
- Only when test execution is reached after a successful upload is it an update target

### 15.6 Result Update Behavior

- Upsert only the tests that were executed
- Do not change the entries of tests that were not executed

On success (`pass`):
- Update `last_result`, `last_run_at`, and `last_success_at`

On failure (`fail`/`error`, etc.):
- Update only `last_result` and `last_run_at`, and retain the existing `last_success_at`

It is acceptable for old entries to remain due to deletion, rename, or exclusion of tests.
Cleanup of stale entries is not included in the initial specification.

### 15.7 Handling of Peer DUTs

Even in tests that use peer DUTs, only the result of the primary DUT (the sketch in the parent directory) is saved to the state cache.

- The build / upload state of peer DUTs is not recorded
- The `nodeid` does not include the peer name
- Even if a test with the same `nodeid` is executed on multiple boards, only the result of the primary DUT is reflected in the state

### 15.8 Independence from ArduTest

The state cache feature does not depend on ArduTest.

- The state cache can be used even in tests that do not use ArduTest
- Regardless of the presence of the ArduTest fixture, the result of test execution performed on the board is recorded
- An entry is created in the state cache even for basic tests using the standard expect of `pytest-embedded`

### 15.9 CLI Option Additions

To control the state cache feature, add the following to the pytest options.

- `--save-state`: flag form. Save the state only when specified (default: disabled)
- `--save-state-dir`: value-specifying form. Specify the directory to save state.json (default: `.pytest-results`)

Example:

```bash
pytest tests/foo --save-state
pytest tests/foo --save-state --save-state-dir .test-cache
```

If `--save-state-dir` is specified but `--save-state` is not, the state is not saved.

### 15.10 Implementation Considerations

#### 15.10.1 Responsibilities of the plugin Layer

- Capture test results using pytest hooks (such as `pytest_runtest_logreport`)
- Confirmation of build / upload success (skip the state update on failure)
- Determination of whether test execution was performed on the real board
- Finalization of the profile name
- Acquisition of the nodeid
- Reading and writing state.json (file I/O)

#### 15.10.2 File I/O Design

- When state.json does not exist, automatically generate the initial structure
- When the `<save_state_dir>/` directory does not exist, automatically create it
- Race conditions due to concurrent execution of multiple tests (such as pytest-xdist) are out of scope in the initial specification
- Even if the user deletes or manually edits state.json, the test body is not affected

#### 15.10.3 Test Determination

The criteria for determining whether test execution was performed on the real board:

- After the upload phase succeeds, the execution of the test phase is reached
- This determination uses the report where `when == "call"` in `pytest_runtest_logreport`

#### 15.10.4 Finalization of the profile Name

- If `--profile` is explicitly specified, use that value
- If automatically selected (when `--profile` is not specified and there is one profile), use the selected profile name

### 15.11 Out of Scope

- Content versioning or migration mechanisms for state.json are not included in the initial specification
- Automatic detection / deletion of stale entries is not performed
- History files or long-term metrics are not included in the initial specification
- CI-oriented report generation or HTML display is not included in the initial specification
- Override options such as `sketch path` or `fqbn` are not included in the mandatory requirements
- Log output control follows pytest's standard verbosity, and no dedicated options are added

## 16. Test Requirements

### 16.1 Unit Tests

At least the following are verified.

- Option interpretation
- build command generation
- upload command generation
- build path resolution
- Reflection of profile / port
- sketch directory resolution from the test file location
- Switching log output according to `-v` / `-vv`
- define generation from `build_config.toml` and environment variables
- Generation of defines without values from the `[flags]` of `build_config.toml`
- serial port resolution per profile
- runtime port completion for host execution such as `socket://localhost`
- Reading the port from `*.host-arduino.json`
- Not passing the socket URL to the upload port
- Pre-build skip when an unsupported profile is specified
- Resolution of `default_profile` and single-profile automatic selection
- Being able to detect peer DUTs from `peer_*` directories
- Name resolution of `peers["<name>"]`
- Multiple specification and duplicate specification error of `--peer-profile <name>:<profile>`
- Multiple specification and duplicate specification error of `--peer-port <name>:<port>`
- Profile resolution order of peer DUTs
- Port resolution order of peer DUTs
- Skip due to undetermined profile / unresolved port of peer DUTs
- Not preparing peer DUTs in tests that do not use the `peers` fixture
- Device lock mode option parsing and default `auto`
- Device lock key resolution from physical serial ports
- Not locking `socket://...` targets by default
- Lock acquisition after compile and before upload
- Deterministic multi-DUT lock ordering
- Stale lock-file tolerance when the OS lock is not held

### 16.2 Minimal Integration Tests

At least the following are verified.

- Being able to load as a pytest plugin
- Options being visible in `pytest --help` or on the plugin manager
- Fixtures being resolvable

### 16.3 Test Policy

- Avoid real-board dependency
- Design `subprocess.run` to be mockable
- Rather than the success or failure of Arduino CLI execution, first verify the separation of responsibilities and interface stability
- In verifying verbosity integration, it is acceptable to check the log branching within the plugin rather than the standard output itself

## 17. examples Requirements

`examples/` should contain minimal usage examples.

Minimum required content:

- A minimal sketch example
- A minimal pytest test example
- An example execution command
- If necessary, a `pytest.ini` or CLI specification example

The purpose is to show "the minimal connection of build / upload / serial expect".

For examples for the host Arduino core, show the following.

- A host execution profile such as `lang-ship:host:host`
- DUT connection via TCP/IP using `--port=socket://localhost`
- socket URL completion using the `port` of `*.host-arduino.json`
- That host execution is for simple verification of pure logic or serial protocol, and is not a substitute for real-board testing or a build test with a real board profile

For examples for peer DUTs, show the following.

- Automatic detection of peer DUTs via `peer_<name>` directories
- Reference to peer DUTs via `peers["<name>"]`
- Individual specification of peer DUTs via `--peer-profile` / `--peer-port`
- That a peer with `default_profile` operates even without specification, and a peer without it operates only when a profile is explicitly specified

## 18. README Requirements

The README should contain at least the following.

- Overview
- What problem the plugin solves
- What is different from `pytest-embedded-arduino`
- Installation method
- Prerequisites
  - `arduino-cli`
  - board core
  - serial port
- Basic usage
- A minimal test example
- Main options
- Device lock behavior and default `auto` mode
- Log behavior with `-v` / `-vv`
- Design policy
- Candidates for future expansion

## 19. Non-Functional Requirements

### 19.1 Maintainability

- Module boundaries are clear
- subprocess execution and command generation are separated
- Board-specific processing is not mixed in

### 19.2 Extensibility

- It is easy to carve out into a service layer or strategy layer in the future
- The upload implementation is easy to swap per board family
- It is easy to add build properties or artifact resolution rules

### 19.3 Portability

- At least, it does not have unnatural premises assuming Linux / macOS
- It does not depend too strongly on a specific environment in the handling of serial ports or CLI paths

## 20. Perspectives to Incorporate from Reference Implementations

Reference target:

- `https://github.com/tanakamasayuki/pytest-esp32-lib/blob/main/tests/conftest.py`

The perspectives referenced from here are as follows.

- The concept of `run-mode`
- build path separation according to profile
- build execution centered on `sketch.yaml` and `-m/--profile`
- A simple execution model of `arduino-cli compile` / `upload`
- The idea of skipping Python-side test execution during build only
- A structure that places `sketch.yaml` in the same location as `.ino` per runner

On the other hand, the policy of not fixing them as-is is as follows.

- The premise of project-specific dotenv
- ESP32-premised operational know-how
- Option design premised on constraints derived from `pytest-embedded-arduino`
- A structure that consolidates everything into conftest

## 21. API / Implementation Image

The implementation details may be adjusted in subsequent design, but a thin structure like the following is assumed.

- `app.py`
  - `ArduinoCliApp`
  - `ArduinoCliBuildConfig`
  - `build_command()`
  - `compile()`
- `flasher.py`
  - `ArduinoCliFlasher`
  - `ArduinoCliUploadConfig`
  - `upload_command()`
  - `upload()`
- `plugin.py`
  - `pytest_addoption()`
  - build/upload execution fixtures
  - `pytest-embedded` integration fixtures

At this stage, the API names are provisional, and may be adjusted into a form that is natural as a Python package at implementation time.

## 22. Acceptance Criteria

The acceptance criteria of this specification are as follows.

1. `pytest-embedded-arduino-cli` is installable as a Python package
2. It can be auto-loaded or explicitly loaded as a pytest plugin
3. A build layer that calls `arduino-cli compile` exists
4. A flasher layer that calls `arduino-cli upload` exists
5. It has a basic design that uses DUT / serial / expect based on `pytest-embedded`
6. No ESP-specific dependencies are included
7. Minimal unit tests and plugin loading tests exist
8. README and examples exist
9. A sketch that specifies a profile not present in `sketch.yaml` is skipped before build
10. A multi-DUT test specification using `peer_*` directories is defined
11. The profile / port of peer DUTs can be specified by name
12. Device lock is enabled by default in `auto` mode for physical serial upload/test runs
13. Device lock waits after compile and before upload, and is held until DUT use finishes
14. Device lock can be disabled with `--device-lock=off`
15. The enable/disable of state cache saving can be controlled with the `--save-state` option
16. The save destination of state.json can be specified with the `--save-state-dir` option
17. Test state is recorded in state.json per `(profile_name, nodeid)`
18. An entry is created in state.json only for tests executed on the real board
19. The state of peer DUTs is not recorded, and only the primary DUT is recorded
20. The state cache functions without depending on ArduTest, even for basic pytest-embedded tests

## 23. Candidates for Future Expansion

- Swapping the upload strategy per board family
- Port resolution support via `arduino-cli board list` integration
- Automatic artifact discovery and absorption of per-board differences
- Abstraction of monitor / reset control
- Integration of build profiles and the test matrix
- Adding `fqbn` override or sketch path override
- Capability declaration per board core / fqbn

The above is the specification of this project.
