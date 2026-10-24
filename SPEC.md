# pytest-embedded-arduino-cli Specification

[日本語版 (Japanese)](SPEC.ja.md)

## 1. Purpose of This Document

This document is a specification for organizing the requirements of the new Python package / pytest plugin `pytest-embedded-arduino-cli`.

The purpose of this plugin is to provide Arduino build / upload based on `arduino-cli`, while building on top of the core / serial / expect features of `pytest-embedded`.

Explicit multiple-profile / peer combination execution and collection-time applicability checks are specified in [section 24](#24-explicit-multiple-profile--peer-combination-execution).

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
- `pytest-embedded` and `pytest-embedded-serial`, 2.8 or later

`pytest-embedded` is a runtime dependency, not a dev dependency.

The plugin uses private parts of `pytest-embedded`: `_listener_gn`, `_pexpect_fr_gn` and `pexpect_proc_fn` to build peer DUTs, and a replacement of `_SerialRedirectThread` for `socket://` and `arduinomonitor://` ports. The lower bound is the version these were tested with; a new `pytest-embedded` release can require a plugin update.

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

### 10.7 What the Plugin Promises About `sketch.yaml`

The plugin reads only a few keys of `sketch.yaml` itself. Everything else reaches arduino-cli through `--profile` / `-m`, and its behavior is arduino-cli's, not a contract of this plugin.

Read and interpreted by the plugin:

- `profiles` names and `default_profile`, for profile selection (10.4, and the single-profile fallback)
- `profiles.<profile>.port`, as the last fallback of the runtime and upload port (14.5, 13.7)
- `profiles.<profile>.fqbn` and `profiles.<profile>.platforms`, only compared as a whole to share one pluggable-monitor probe between sketches (13.9). Their meaning is not interpreted.

Profile names must give distinct port variables. The plugin treats these as configuration errors:

- Two profiles in one `sketch.yaml` whose names become the same after upper-casing and replacing `-` with `_`, such as `esp32-s3` and `esp32_s3`
- A profile whose name becomes `PEER_...`, because `TEST_SERIAL_PORT_PEER_...` belongs to peer DUTs

Passed through to arduino-cli and not promised by the plugin:

- `port_config`, board options, programmers, and platform resolution, including a `platforms` entry without a version
- `default_port_config` at the top level, which arduino-cli does not apply when a profile is selected
- `--baud` does not apply to a runtime port read through `arduino-cli monitor`; its settings come from arduino-cli

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
- The key is the port string. Filesystem paths are resolved through symlinks (`/dev/serial/by-id/...` locks the same device as `/dev/ttyUSB0`); other forms, such as `wchlink://...` or `oep://...`, are used as written. The plugin cannot know that `wchlink://S` and `/dev/ttyACM3` are the same probe, or whether two `oep://` slots share hardware. Projects that address one device in several ways set the same `--device-lock-key` on each run.

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

This file is a contract between repositories: host Arduino cores write it, and this plugin reads it. The file name pattern and the `port` key are kept stable; new keys may be added and are ignored by the plugin.

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
4. `profiles.<profile>.port` of `peer_<name>/sketch.yaml`
5. If it cannot be resolved, skip the test that requires that peer DUT

`<NAME>` and `<PROFILE>` are in a form that is uppercased and has `-` replaced with `_`.
For example, the `host` profile of `peer_echo` refers to `TEST_SERIAL_PORT_PEER_ECHO_HOST`.
When two peers of one test would read the same variable, such as `peer_a_b` with profile `c` and `peer_a` with profile `b_c` (both `TEST_SERIAL_PORT_PEER_A_B_C`), or `peer_a-b` and `peer_a_b`, it is a configuration error.

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

The order of build / upload is as follows.

1. Build the primary DUT
2. Build detected peer DUTs in name order
3. Upload the primary DUT

After that, the function-scoped `dut` and `peers` fixtures are set up in the order the test function lists them. The plugin does not fix an order between them.

- `dut`: connect to the primary DUT through the normal processing of pytest-embedded
- `peers`: upload the detected peer DUTs in name order, perform runtime port completion, connect to them, and provide them as `peers["<name>"]`

In this order, the Python side may miss the startup message that the real-board DUT outputs only briefly immediately after upload.
In environments where the output is retained until the socket connection, such as the host Arduino core, this is unlikely to be a problem, but for general real-board serial, it is recommended to prepare sufficient waiting, retransmission, or a handshake on the sketch side that waits for input from the Python side.
Especially for peer DUTs, since all detected peers are started when the `peers` fixture is requested, tests that depend on the startup order between DUTs synchronize via the sketch-side protocol.

Structural defects of peer DUTs are treated as configuration errors.
For example, if there is no `.ino`, there are multiple `.ino` files, or the `sketch.yaml` is broken, it is treated as an error.
On the other hand, if the execution conditions are not met, such as unsupported profile, undetermined profile, or unresolved port, it is treated as skip.

### 13.9 Runtime Connection Through a Platform's Pluggable Monitor

Some platforms deliver the runtime console through their own pluggable monitor, not a plain serial port (for example, a debug probe that selects the source with a monitor setting). Opening such a port with pyserial bypasses that monitor, so the plugin reads the runtime port through `arduino-cli monitor` for those platforms.

Detection:

- The plugin runs `arduino-cli compile --show-properties --profile <profile>` for the sketch under test. With a profile, arduino-cli reads the platform version the profile pins.
- The port's protocol is `serial` for a plain path such as `/dev/ttyACM0` or `COM3`, and the scheme for a port written as `<scheme>://...`, such as `wchlink://FBC18F0680B0` or `oep://<probe>/<slot>` reported by the platform's pluggable discovery.
- The platform has its own monitor for that protocol when `pluggable_monitor.pattern.<protocol>` is set, or when `pluggable_monitor.required.<protocol>` names a tool that does not start with `builtin:`. `builtin:serial-monitor` is the default arduino-cli fills in for platforms without one, and it is not counted.
- A URL whose scheme the platform has no monitor for, such as `rfc2217://...`, is left to pyserial. `socket://...` (the host core) is always left to pyserial and not probed.
- The result is cached per board for the session. Sketches whose profiles have the same `fqbn` and `platforms` share one probe. A sketch without a profile is probed on its own.
- The choice is automatic and there is no option to override it. Tests keep using `dut` and `peers`; there is no separate fixture and no marker.

Connection:

- The runtime port becomes an `arduinomonitor://<address>?...` URL. Its text is not part of the API; code that needs the address, protocol or profile parses it with `pytest_embedded_arduino_cli.MonitorTarget.from_url` (21). The plugin registers a pyserial protocol handler for that scheme, so `dut`, `peers`, `dut.write`, `expect`, and the logs work unchanged.
- The handler starts `arduino-cli monitor -p <address> -l <protocol> --quiet -m <profile>` with the sketch directory as the working directory, and pipes stdin and stdout. Both directions pass bytes unchanged. stderr is kept apart from the data.
- stdin stays open for the whole session. arduino-cli ends the session when stdin reaches EOF. Bytes written before the monitor has opened the port are delivered once it has.
- Port settings are left to arduino-cli: board defaults from `monitor_port.serial.<id>` in `boards.txt`, overridden by the profile's `port_config` in `sketch.yaml`. The plugin adds no option for them, and `--baud` does not apply to this connection. With a profile, a top-level `default_port_config` in `sketch.yaml` is not applied by arduino-cli. A key the monitor does not declare makes arduino-cli stop before the session opens.
- Closing closes stdin, which makes arduino-cli send `CLOSE` to the monitor tool and exit. If arduino-cli has not exited within a few seconds, it is terminated. The monitor tool runs in a process group of its own; it is expected to exit when its stdin reaches EOF.
- If the stream ends while the plugin has not closed it, reading raises a serial error with arduino-cli's exit code and stderr, and the error is logged. The plugin does not reconnect or restart the monitor. When the monitor fails to open the port, arduino-cli's stderr carries the monitor's message.
- Opening takes about one second, and arduino-cli starts the monitor tool twice (once to list its settings, once for the session). Output the board prints before the session opens is not received, as with any connection opened after upload.

The `arduino_cli_build_properties` fixture (module scope) returns the same `--show-properties` result as a `dict[str, str]`, run once per sketch and profile. It is generic: other plugins can use it to read, for example, `runtime.tools.<tool>.path` of the platform under test. Values injected from `build_config.toml` are not included.

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

The compile-related options specific to this plugin are `--profile` and `--clean`.

`--clean` has two roles: it passes `--clean` to `arduino-cli compile`, and it removes the ArduTest artifact directory before the run. Both are kept in one option.
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

The runtime port is resolved in the following priority order.

1. `--port`
2. Environment variable per profile
3. Common environment variable
4. `profiles.<profile>.port` in `sketch.yaml`

The upload port is `--flash-port` when given, and otherwise the runtime port. A `socket://...` runtime port is not passed to `arduino-cli upload --port`.
`--flash-port` is never used as the runtime port.

The environment variable name per profile is in a form that normalizes the profile name, such as `TEST_SERIAL_PORT_ESP32S3`.
The common environment variable is `TEST_SERIAL_PORT`.

If a socket URL such as `socket://localhost` is specified in `--port` or an environment variable, it is treated as the runtime connection target.
A socket URL without a port number is completed by reading the `port` from the `*.host-arduino.json` in the build output directory after upload.
A socket URL with a port number is used directly without completion.

When the platform has its own pluggable monitor for the runtime port's protocol (`serial` for a plain path, the scheme for `wchlink://...` and the like), the runtime port is read through `arduino-cli monitor` instead of being opened with pyserial (see 13.9).

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
- Keep plugin-specific options small and scoped to execution mode, profile selection, peer DUTs, device locking, ArduTest, local state cache, and the log directory summary
- `--port`, `--flash-port`, and `--baud` belong to `pytest-embedded`. The plugin reads them and may write the resolved runtime port back into `--port` for the current module
- Existing option names are kept even where their prefixes differ, such as `--arduino-cli-no-log-summary`

### 14.9 Log Directory Result Summary

`pytest-embedded` owns the log directory `<tmpdir>/pytest-embedded/<UTC timestamp>/<test name>/`, and only serial logs are written there.
The result of the run is therefore not visible from the directory tree, so this plugin adds result files to the same directory.

- Write exactly one status file per test directory: `PASSED.txt`, `FAILED.txt`, `ERROR.txt`, `SKIPPED.txt`, `XFAILED.txt`, or `XPASSED.txt`
  - `ERROR.txt` covers setup / teardown failures, which is where build and upload failures appear
  - The status file holds the test id, per-phase durations, the profile, the log file names, and the failure text when there is one
  - Remove status files left by a previous run in the same directory so the tree never shows a contradiction
- Write a zero-byte marker at the session log directory root whose name carries the counts, such as `FAILED-2_PASSED-7`, so a single `tree` or `ls` line shows the outcome
- Write `SUMMARY.txt` for humans and `summary.json` for machines, both covering the whole run
- Truncate failure text to a bounded size, keeping the tail; `dut.log` in the same directory remains the complete serial log
- Never write anything when `pytest-embedded` did not create a log directory, and never let a failure in this feature affect the pytest exit status
- Option: `--arduino-cli-no-log-summary` disables the feature. The default is enabled

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
- Single-execution `nodeid` does not include the peer name. Combination mode in section 24 includes peer profiles to distinguish configurations
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
- Check the item's successful upload and entry into the call phase, then finalize the result on the teardown report. A teardown failure records error without advancing this run's success timestamp

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
- Status file, root marker, `SUMMARY.txt`, and `summary.json` contents of the log directory summary
- Replacement of stale status files and markers from a previous run
- Worst-status selection when several test ids share one log directory name
- Disabling the log directory summary with `--arduino-cli-no-log-summary`

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

## 21. Public API

These names are the plugin's public API and follow semantic versioning.

- Fixtures
  - `arduino_cli_app` (module): the resolved `ArduinoCliBuildConfig`
  - `arduino_cli_flasher` (module): the resolved `ArduinoCliUploadConfig`
  - `arduino_cli_build_properties` (module): `dict[str, str]` of `arduino-cli compile --show-properties` for the sketch and profile under test (13.9)
  - `arduino_test` (function): the ArduTest session ([`ARDUTEST_PYTEST_SPEC.md`](ARDUTEST_PYTEST_SPEC.md))
  - `peers` (function): a mapping of peer name to DUT (13.8)
- Python
  - `pytest_embedded_arduino_cli.MonitorTarget`: parses an `arduinomonitor://` runtime port with `MonitorTarget.from_url(port)` and builds one with `to_url()`. Fields: `address`, `protocol`, `profile`, `sketch_dir`, `cli_path`
  - `pytest_embedded_arduino_cli.is_monitor_url(port)`
- Options (section 14) and environment variables (14.5, 13.7)
- The `*.host-arduino.json` file (13.4)

The text of an `arduinomonitor://` URL is not part of the API. Code that needs the address or the profile behind a runtime port parses it with `MonitorTarget.from_url` instead of slicing the string.

Other modules and functions, including `app.py`, `flasher.py`, `serial.py`, and the helpers in `plugin.py`, are internal and may change in any release.

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

The following section specifies execution across multiple profiles and peer combinations.

## 24. Explicit Multiple-Profile / Peer Combination Execution

### 24.1 Status and Purpose

The features in this section are implemented for the next release.
Preserve single-profile behavior from baseline `a50b0de8b47a` and expand execution configurations within one pytest session only when explicitly requested.
This section defines combination-mode differences from the single-configuration rules in sections 6, 13, 14, and 15. Collection-time applicability checks also work for single execution and ordinary Python tests.

- The plugin owns candidate expansion, the DUT lifecycle per configuration, skip decisions, and result identity.
- The consuming project owns profile definitions, physical device assignments by role, and functional / wiring applicability.
- CI job partitioning and artifact aggregation across jobs remain external responsibilities.
- Do not add equipment discovery, automatic wiring changes, a device farm, or parallel hardware execution.
- Do not add a custom matrix configuration file or custom fields to `sketch.yaml`.

### 24.2 CLI and Candidate Selection

Options:

| Option | Meaning |
|---|---|
| `--profiles=all` | Select every profile defined for each primary sketch |
| `--profiles=esp32,esp32s3` | Limit primary candidates to the specified names; one name is also valid |
| `--peer-profiles=all` | Select every profile for each peer sketch used by the test |
| `--peer-profiles=echo:esp32,esp32s3` | Limit a named peer to the specified profile candidates |
| `--peer-profiles=echo:all` | Select every profile for that named peer only |

Named `--peer-profiles` options may be repeated for different peers. Peers without a selection retain their existing resolution rules.
Bare `--peer-profiles=all` is a special selection for all peers and cannot be combined with named selections or the existing `--peer-profile` option.
Reject `--profiles` together with the existing `--profile`, and reject `--peer-profiles` together with the existing `--peer-profile` for the same peer.
Named multiple selections and existing single selections may be combined for different peers.

| Primary selection | Peer selection | Execution set |
|---|---|---|
| No new option | No new option | Existing single configuration |
| `all` | Unspecified | All primary candidates × peer default / existing explicit selection |
| Unspecified | `all` | Primary default / existing explicit selection × all peer candidates |
| `all` | `all` | Cartesian product of all candidates on both sides |
| Explicit candidates | Explicit candidates | Cartesian product of the specified candidates only |

Without a new selection, preserve primary resolution through `--profile` → `default_profile` → single-profile fallback, and peer resolution through `--peer-profile` → `default_profile`.
A missing default must not trigger expansion to all candidates. Do not add single-profile auto-selection for peers.
Selecting `all` only for the primary does not expand peer candidates.
With multiple peers, each peer's candidates form a separate axis of the Cartesian product.
Reserve `all` in the new options; an actual profile named `all` remains selectable through the existing `--profile all` / `--peer-profile <name>:all` options.

This section calls an invocation using either new option “combination execution mode.” Its preflight rules apply even when only one candidate is selected.

### 24.3 Collection and Input Validation

Identify a configuration by the primary profile and a mapping of used peer profiles sorted by peer name.
Use existing sketch resolution to read the `sketch.yaml` resolved for each sketch. Do not silently remove collected items based on environment variables or equipment availability.

- `all` enumerates definitions local to each resolved sketch configuration. Do not multiply every sketch by the union of profiles across all sketches.
- If an explicit candidate is unsupported by an individual sketch, retain a skip item identifying the configuration and reason.
- If an explicitly requested profile name exists in none of the targeted sketches, report an input error. Validate primary and named peer selections separately.
- Reject empty lists, duplicate candidates, duplicate selections for one peer, unknown peer names, mixing `all` with names, and malformed configuration.
- Report an error if an `all` target has no profiles or if no structurally valid configuration exists among the selected Arduino targets. Distinguish this from all configurations being skipped for missing ports.
- Do not multiply ordinary Python tests without a neighboring `.ino` by the profile count.
- Bare `--peer-profiles=all` adds no peer axis to modules without peers. Validate unknown names in named peer selections against the collected targets as a whole.
- Do not multiply tests that do not require `peers` by peer combinations, or skip them for missing peer ports. Account for indirect fixture dependencies.
- In modules mixing tests with and without peers, generate only the needed configurations and do not repeat a peer-free test for the same primary profile.
- Candidate ordering and IDs must be deterministic and must not collide when combined with existing test parameters.

IDs use `primary=<profile>,<peer>=<profile>,...`, with peers sorted by name. Delimiters inside names are percent-encoded; unresolved profiles use `<unresolved>`. Existing parameter IDs can be combined with these IDs. Example display:

```text
test_link[primary=esp32,echo=esp32]
test_link[primary=esp32,echo=esp32s3]
test_link[primary=esp32s3,echo=esp32]
test_link[primary=esp32s3,echo=esp32s3]
```

`--collect-only` enumerates planned items and validates static configuration only. It must not connect to equipment, request plans from external equipment services, build, upload, start monitors, or acquire device locks.
Collection must not delete existing artifacts even when `--clean` is also specified.

### 24.4 Port Resolution and Preflight Skips

In combination execution mode, check the connection assignments for all required primary / peer roles before the first DUT upload.
Skip deficiencies detectable from configuration before compilation to avoid unnecessary builds.

| Condition | Behavior in combination execution mode |
|---|---|
| Unresolved runtime port for a required primary / peer | Skip, identifying the configuration and missing role |
| Different roles in one configuration use the same physical DUT | Skip, identifying the conflicting roles |
| Connection failure on a configured port, compile failure, or upload failure | Error; do not convert into a missing-configuration skip |
| Lock acquisition failure / timeout | Error; do not treat as an unconfigured port |
| `--run-mode=build` | Compile without applying missing-port or duplicate-device skips |
| Host core | Include when socket configuration resolves; do not require a physical serial port |

Check whether a connection target resolves, not merely whether an environment variable exists. Profile-specific environment variables and `profiles.<profile>.port` remain usable.
For a role with multiple candidates, do not automatically reuse a profile-independent common port across different chips.
Reject common CLI port assignments for that role (primary `--port` / `--flash-port`, or peer `--peer-port`) and disables its common environment-variable fallback.
A role with one candidate retains the existing port resolution order. Invocations without the new options retain existing port resolution and error / skip behavior.
This restriction does not prohibit explicitly assigning the same port in profile-specific configuration: different execution configurations may use the same DUT sequentially.

Duplicate detection must use physical identity consistent with device locking, including symlink resolution, rather than just port-string equality.
Check peer-to-peer as well as primary-to-peer conflicts. Account for separate upload / runtime ports when their relationship is known.
Discovering whether arbitrary different port representations refer to the same device is out of scope; the consuming project supplies correct assignments.
Identical dynamic host placeholders such as `socket://localhost` alone must not cause a duplicate-physical-DUT skip.
Preserve the distinction between upload and runtime targets and the existing rule that socket URLs are not passed as upload ports.

A separate new skip-policy option is not required; these behaviors belong to combination execution mode.
The consuming project checks external wiring / capabilities and, when needed, integrates that check before the first upload. Do not embed OEP-specific or other equipment-specific APIs in the plugin.

### 24.5 Four-Device / Three-Device Examples

Assume both the primary sketch and `peer_echo` define `esp32` and `esp32s3`.
With two ESP32 devices and two S3 devices, assign role-specific environment variables as follows, using actual ports as values.

| Environment variable | Assignment |
|---|---|
| `TEST_SERIAL_PORT_ESP32` | Primary ESP32 |
| `TEST_SERIAL_PORT_ESP32S3` | Primary S3 |
| `TEST_SERIAL_PORT_PEER_ECHO_ESP32` | Peer ESP32 |
| `TEST_SERIAL_PORT_PEER_ECHO_ESP32S3` | Peer S3 |

```bash
# collect and execute four configurations per test
pytest tests/link --profiles=all --peer-profiles=all

# restrict the peer to ESP32 and collect two configurations per test
pytest tests/link --profiles=esp32,esp32s3 --peer-profiles=echo:esp32
```

With two ESP32 devices and one S3 device, assign the S3 to the primary role and leave the peer S3 port unconfigured.
Assuming the peer's S3 profile also has no port assignment, the first command collects four configurations, executes two, and skips the two requiring an S3 peer.
The second command collects only two configurations from the outset.
Distinguish excluding a profile from the candidate set from including it in the plan and recording an equipment-related skip.

### 24.6 Fixture and Resource Lifecycle

Do not implement this by repeatedly overwriting session-wide profile options or by looping inside test bodies.
Introduce a module-scoped execution-configuration parameter and make app, build properties, build / upload, monitor, port, peer, and lock lifecycles depend on it.
Group tests for the same module / configuration where possible, tearing down dependent fixtures before preparing the next configuration.

- Move peer compiled / uploaded caches stored on module objects into configuration-specific state, or reliably clear them.
- Do not reuse a resolved runtime port or monitor URL as input to the next configuration. Limit the pytest-embedded integration to the configuration's lifetime as well.
- After preflight and compilation, acquire the required physical device locks in a deterministic order before the first upload.
- Hold locks through DUT connection use and consuming-project cleanup; release acquired resources even on partial setup failure.
- If one cleanup fails, attempt to release other resources and attribute the teardown error to that configuration. Do not proceed unconditionally if shared resources could not be safely released.
- Keep duplicate-device feasibility checks separate from exclusion against other processes through device locks.
- Assume sequential execution; xdist / parallel hardware execution support is separate work.

Preserve the roles of `--run-mode=all` / `build` / `test`. As before, a successful build-only run consists of successful compilation and skipped test bodies, not successful hardware verification.
Keep existing sketch / profile build-path separation as the baseline. Initially, do not add a plugin-level cache that omits compilation; use Arduino CLI's normal incremental builds.
Any future compile-elision cache must validate actual inputs, including sources, core / libraries, build properties / defines, rather than profile names alone.

### 24.7 Results, Artifacts, and State Cache

Bind the configuration to the item before setup starts and to every phase report.
Do not infer result ownership from the “last used profile” on the current config.

- Include the configuration in nodeids and attribute setup errors, skips, call outcomes, and teardown errors to it.
- Identify configurations in serial logs, ArduTest artifacts, JUnit, and summaries. Do not overwrite identically named artifacts from different modules / parameters / peer configurations.
- Build on JUnit and existing summaries without adding a large custom reporting framework.
- Distinguish the selected planned items from completed results. Do not fabricate passed / skipped outcomes for items not executed because of interruption or `--maxfail`. Collection alone is not execution.
- Do not describe all-skipped equipment runs as fully verified. Preserve pytest's standard exit codes; CI requirements for mandatory configuration coverage remain with the consuming project.
- Continue updating `--save-state` only for verification that reached the test body. Unexecuted items, skips, and build / upload failures must not update previous results.
- Preserve the primary-profile grouping of state; in combination mode, nodeids including peer profiles distinguish results. This does not add standalone peer verification histories.
- Do not change nodeids or state keys for single execution without the new options. Do not implicitly merge or equate records from single and combination execution.

### 24.8 Change Scope and External Runner Alternative

The main targets are options / collection / fixtures / reports in `plugin.py`, candidate resolution in `app.py`, target resolution and duplicate checks in `serial.py` / `device_lock.py`, and artifact destinations in `log_summary.py` and ArduTest.
Also check state-cache eligibility and keys, and compatibility with pytest-embedded fixtures / log directories.

Keep an external runner invoking existing single-profile pytest subprocesses as a migration alternative.
Such a runner separates JUnit, artifacts, and caches per configuration and bundles results with a manifest recording planned launches, termination status, interruptions, and configurations not launched.
The existing plugin does not skip a missing primary port; if a runner omits a launch, record that separately from a pytest skip.
This change does not implement a runner. The chosen direction is expansion inside the plugin so routine listing, selection, and partial reruns work within one pytest session.

### 24.9 Implementation Stages and Acceptance Criteria

1. Design the internal configuration as a primary plus peer mapping. First implement peer-free list / `all` selection, item IDs, fixture switching, and result separation.
2. Extend that same model with peer Cartesian products, preflight skips for unresolved ports / duplicate devices, and peer lifecycle management.
3. Verify artifacts / summaries / state and compatibility with existing parameters, selection, and reruns; update the existing specification sections and guides in both languages.

Verify at least the following. Keep compilation / upload / connections mockable, with hardware smoke tests performed separately.

- No regressions for defaults, single profiles, peer defaults / explicit selections, or existing error / skip behavior without the new options.
- Two profiles × two tests without peers can be collected; a build failure in one profile is correctly attributed and the other executes independently.
- Both-side `all` produces four configurations in the four-device example; the three-device example gives two executions / two skips; an explicit ESP32-only peer gives two configurations.
- Multiple-peer products, peer-to-peer physical conflicts, indirect `peers` dependencies, and mixed peer / peer-free tests are handled.
- Missing ports, unsupported profiles, and consuming-project equipment checks take effect before the first upload and retain the necessary skip reasons.
- Alternate symlinks for the same device are detected, without incorrectly skipping sequential reuse across configurations or dynamic host sockets.
- Build-only works without ports; collect-only performs no equipment operations, compilation, or artifact deletion.
- Setup / teardown failures, connection targets and firmware after switching, lock release, and peer-cache isolation are verified.
- Configuration IDs remain stable with exact nodeid selection, `-k`, `--lf` under the same candidate selection, and existing `parametrize` usage.
- Units without `.ino` are not duplicated; logs / ArduTest artifacts / JUnit / state distinguish results with different peer profiles.
- Interruptions, `--maxfail`, and all-skipped runs are not confused with completed or fully successful execution.

### 24.10 Collection-Time Applicability API

Normally select execution scope through profile candidates; use applicability exclusions only for special restrictions that the candidate product cannot express.
Expose these APIs so consuming projects can declare constraints such as unsupported cross-wired pairs. The plugin does not own equipment semantics or wiring tables.

- `ArduinoCombination`: read-only `primary: str | None` and `peers: Mapping[str, str | None]`, importable from `pytest_embedded_arduino_cli`.
- `pytest.mark.arduino_skip_if(predicate, reason="...")`: skip when `predicate(item, combination)` returns `True`. Require an actual `bool` and a nonempty reason. Supported at module / class / function / parameter scope.
- `pytest_arduino_cli_skip_reason(item, combination)`: a hookspec implemented in `conftest.py` or a plugin. Return a nonempty reason `str` or `None`. Hook wrappers are unsupported.

Apply both APIs to collected items remaining after selection such as `-k` / `-m` / `--lf`. `item` exposes test names, nodeid, path, markers, and pytest config.
For items without an Arduino sketch, `combination` is `None`. Peer-free tests have an empty `peers` mapping; unresolved profile values are `None`.
These APIs also apply without the new profile options and do not change single-execution nodeids.

Invoke only hook implementations applicable to the item's directory; sibling `conftest.py` files must not interfere.
Parent / child hooks and all markers accumulate. Any exclusion adds a standard skip marker; `False` / `None` cannot remove other restrictions.
Reasons include the marker's declaring node and predicate source, or the hook implementation source.
Evaluate every rule. Even after an earlier exclusion, exceptions, invalid return values, or `pytest.skip()` inside a rule stop execution as configuration errors before build.
Rules must only read static configuration: no equipment communication, fixture requests, or config mutation. Evaluate them under `--collect-only` and display applicability skips with reasons. Runtime port preflight is not performed during collection.

Decide skips before module fixture setup, avoiding compile / upload solely for an excluded item. A separate eligible item may still require building the same firmware.
Guides distinguish candidate selection, inapplicability, equipment shortages, failures, and interruptions. A skip is not successful verification or proof of coverage; do not recommend hiding known defects through exclusions.
See [Advanced Testing](TESTING_ADVANCED.md#profile-combinations-and-applicability) for examples.

The above defines the project specification.
