# ArduTest pytest Integration Specification (Draft)

[日本語版 (Japanese)](ARDUTEST_PYTEST_SPEC.ja.md)

## 1. Overview

This specification defines the requirements for the `arduino_test` fixture provided by `pytest-embedded-arduino-cli`.

The `arduino_test` fixture communicates with the Arduino-side library `ArduTest` and is responsible for retrieving the test list, evaluating requirement / config, running tests, collecting results, and reflecting them into the pytest result.

The command / event / payload format of the communication protocol is defined in [`ARDUTEST_PROTOCOL_SPEC.md`](ARDUTEST_PROTOCOL_SPEC.md). This specification covers the pytest-side public API, configuration resolution, the execution lifecycle, and how results are reflected into pytest.

---

## 2. Goals

- ArduTest tests written on the Arduino side can be run from pytest
- requirement / config requirement can be evaluated before execution to determine whether a test can run
- Arduino-side pass / fail / error can be reflected into the pytest result
- Logs, metrics, and artifacts can be saved and referenced on the pytest side
- Existing tests that use the `dut` fixture are not affected

---

## 3. Non-Goals

- Replacing `dut.expect(...)`
- Replacing the Unity output parser
- Defining the Arduino-side library API
- Directly controlling external measurement instruments
- Device farm or parallel control of multiple boards

---

## 4. Positioning of the fixture

`arduino_test` is a high-level fixture added on top of `pytest-embedded-arduino-cli`.

```python
def test_board(arduino_test):
    arduino_test.run()
```

Internally, it may use the following.

- `arduino_cli_app`
- `arduino_cli_build`
- `arduino_cli_upload`
- `dut`
- `pytest-embedded-serial`

However, it does not affect tests in which the user uses `dut` directly as before.

---

## 5. Public API

### 5.1 `arduino_test.run()`

Runs all runnable ArduTest tests.

```python
def test_board(arduino_test):
    arduino_test.run()
```

Behavior:

- Performs initial synchronization if necessary
- Retrieves the test list
- Evaluates requirement and config requirement
- Runs the non-skipped tests one by one
- Reflects any failed or error into a pytest failure
- Reflects skipped into the pytest report

### 5.2 `arduino_test.run(name)`

Runs only the single specified ArduTest test.

```python
def test_wifi(arduino_test):
    arduino_test.run("test_wifi_connect")
```

If the specified name does not exist, it is treated as a pytest error.

### 5.3 `arduino_test.list_tests()`

Performs initial synchronization and `LIST`, and returns the test metadata from the device.

```python
tests = arduino_test.list_tests()
```

The return value is a Python-side dataclass or an equivalent read-only object.

Expected fields:

- `name`
- `requirements`
- `required_configs`

### 5.4 `arduino_test.set_config(name, value)`

Explicitly sets, within a pytest test function, the value passed to an ArduTest required config.

```python
def test_sample_rate(arduino_test):
    arduino_test.set_config("sample_rate", 1000)
    arduino_test.run("test_sample_rate")
```

`value` is stringified with `str(value)` and sent to the device.

If the same name is set multiple times, the last one wins.

### 5.5 `arduino_test.set_capability(name, enabled=True)`

Explicitly sets, within a pytest test function, whether an ArduTest requirement is satisfied.

```python
def test_measurement(arduino_test):
    arduino_test.set_capability("measurement.current")
    arduino_test.run("test_measurement")
```

If the same name is set multiple times, the last one wins.

### 5.6 `arduino_test.reset()`

Performs a device reset or a protocol state reset.

In the initial implementation, whether a physical reset occurs follows the existing reset capability of `pytest-embedded-arduino-cli`. When a protocol-only reset is possible, it sends `RESET_STATE`.

### 5.7 Collected data

After execution, the following can be referenced.

```python
arduino_test.results
arduino_test.logs
arduino_test.metrics
arduino_test.artifacts
```

In the initial implementation, these are held as attributes on the fixture instance. How they are attached to the pytest report is considered separately.

---

## 6. Internal Data Model

### 6.1 Test metadata

```python
ArduTestCase(
    name: str,
    requirements: tuple[str, ...],
    required_configs: tuple[str, ...],
)
```

### 6.2 Test result

```python
ArduTestResult(
    name: str,
    status: Literal["passed", "failed", "skipped", "error"],
    failures: list[ArduTestFailure],
    logs: list[str],
    metrics: dict[str, int | float],
    artifacts: list[ArduTestArtifact],
    duration: float,
    skip_reason: str | None,
)
```

### 6.3 Artifact

```python
ArduTestArtifact(
    test_name: str,
    filename: str,
    content_type: str,
    path: Path,
)
```

---

## 7. Execution Lifecycle

### 7.1 Normal execution

```text
1. pytest fixture setup
2. arduino-cli build / upload follows the existing autouse fixtures
3. Establish dut / serial connection
4. protocol HELLO
5. Retrieve test metadata with LIST
6. Evaluate capability / config
7. Send config to the device
8. Send RUN one by one
9. Collect events
10. Reflect into the pytest result
```

### 7.2 lazy sync

`arduino_test` need not communicate with the device when the fixture is created. It performs initial synchronization at the point `run()` or `list_tests()` is called.

Reasons:

- Merely taking the `arduino_test` fixture as an argument does not consume serial
- Leaves room for users who want to control things themselves
- Does not assume a device connection at the pytest collection stage

### 7.3 Running multiple times

When `run()` is called multiple times within the same pytest test function, the initial synchronization result may be reused.

`set_config()` / `set_capability()` are referenced when `run()` builds its execution plan. When values are changed after `run()` and `run()` is called again, the test metadata may be reused, but config / capability evaluation is re-run.

---

## 8. Reflecting into the pytest result

### 8.1 status mapping

| ArduTest status | Handling on the pytest side |
| --- | --- |
| `passed` | pass |
| `failed` | assertion failure |
| `error` | pytest error or failure |
| host-side `skipped` | skip report |

In the initial implementation, when multiple ArduTest tests are run within a single pytest test function, if any is failed / error, the entire pytest test function is treated as a failure.

### 8.2 Displaying multiple test results

On failure, `arduino_test.run()` includes a summary in the pytest failure message containing the following.

- The test name of the failed / error
- The file / line / expression of the assertion failure
- The code / message of the protocol error
- The number of skipped tests

### 8.3 Splitting into pytest items

The approach of collecting each ArduTest test case as a pytest item is not adopted in the initial implementation.

Reasons:

- It requires a device connection and firmware execution at the pytest collection stage
- It tends to conflict with the build / upload / serial lifecycle
- A fixture API is simpler in the initial implementation

In the future, it may be considered as an opt-in feature such as `--arduino-test-collect`.

---

## 9. capability

### 9.1 requirement evaluation

The requirements retrieved from the device are matched against the host-side capabilities.

Tests with requirements that are not satisfied are not `RUN` and are treated as skipped.

### 9.2 Sources and precedence

capability is resolved in the following order.

1. `arduino_test.set_capability(name, enabled)`
2. Environment variable `ARDUINO_TEST_CAP_<NAME>`
3. false if unset

Fixed values and test-local assumptions are made explicit with `set_capability()`. Values that depend on the real hardware or the CI environment are passed via environment variables.

### 9.3 Environment variables

For environment variables, the following format is supported.

```text
ARDUINO_TEST_CAP_<NAME>=true
```

Normalization:

- `.`, `-`, and `:` in requirement names are converted to `_`
- Case is not distinguished

Examples:

```text
measurement.current -> ARDUINO_TEST_CAP_MEASUREMENT_CURRENT
network -> ARDUINO_TEST_CAP_NETWORK
```

Values regarded as true:

- `1`
- `true`
- `yes`
- `on`

Values regarded as false:

- unset
- `0`
- `false`
- `no`
- `off`

Any other value is treated as a configuration error and becomes a pytest error.

### 9.4 pytest option

A pytest option for capability is not added in the initial implementation.

Reasons:

- capability is a condition of the environment under test, and fits well with `.env` and CI variables
- Fixed values can be made explicit within a pytest test using `set_capability()`
- Avoids adding too many plugin options

---

## 10. config

### 10.1 config sources

config is resolved in the following order.

1. `arduino_test.set_config(name, value)`
2. Environment variable `ARDUINO_TEST_CONFIG_<NAME>`
3. unset

Fixed values and test-local values are made explicit with `set_config()`. Environment-dependent values such as serial port, connection target, secrets, and hardware-specific values are passed as environment variables from `.env` or CI variables.

### 10.2 Environment variables

For environment variables, the following format is supported.

```text
ARDUINO_TEST_CONFIG_<NAME>=value
```

The normalization rules are the same as for capability.

Examples:

```text
ssid -> ARDUINO_TEST_CONFIG_SSID
wifi.password -> ARDUINO_TEST_CONFIG_WIFI_PASSWORD
```

### 10.3 Missing required config

When a config declared by `REQUIRE_CONFIG` is not found, it is treated as skipped by default.

This can be switched to error handling with the following option.

```text
--arduino-test-missing-config=skip|error
```

### 10.4 Sending to the device

The host sends only the config required by the tests to be run, via `SET_CONFIG`.

When the same config is required by multiple tests, it may be sent only once.

### 10.5 pytest option

A pytest option for config is not added in the initial implementation.

Reasons:

- config tends to be an environment-dependent value, and fits well with `.env` and CI variables
- Fixed values can be made explicit within a pytest test using `set_config()`
- Avoids adding too many plugin options

---

## 11. logs / metrics / artifacts

### 11.1 logs

`LOG` events are held in association with the test result.

Whether to display them in pytest's `-s` or verbose mode may be made an option separately.

### 11.2 metrics

`METRIC` events are saved per test name.

When the same metric name is sent multiple times, whether it is held as a list or only the last value is retained is left undecided in the initial implementation.

### 11.3 artifacts

`ARTIFACT_TEXT` / `ARTIFACT_BINARY` are saved as files. `ARTIFACT_TEXT` is saved as UTF-8 text, and `ARTIFACT_BINARY` saves the payload bytes as-is without decoding.

The destination root can be specified with a pytest option.

```text
--arduino-test-artifact-dir=PATH
```

The default value is `ardutest`.

When `PATH` is a relative path, it is resolved as a path relative to pytest's `rootdir`. Therefore the default destination is `<pytest rootdir>/ardutest`.

Save layout:

```text
<artifact-dir>/<test-name>/<filename>
```

`<artifact-dir>` is created automatically at the point an artifact needs to be saved. A run in which no artifact occurs does not create an empty artifact directory.

In the initial implementation, it does not depend on pytest's `tmp_path`-family fixtures; instead it determines a stable destination from the artifact root specified by the option and `request.node`.

When `--clean` is specified, `<artifact-dir>` is deleted as a whole directory before the tests run. After that, as in a normal run, the directory is not recreated until the point an artifact needs to be saved.

The filename is validated according to the protocol specification.

---

## 12. timeout / reset / error

### 12.1 timeout

timeout is determined on the host side.

Recommended option:

```text
--arduino-test-timeout=30
```

The unit is seconds. The initial value candidate is 30 seconds.

### 12.2 protocol error

The following are treated as protocol errors.

- Unknown event
- Mismatch in the number of fields
- Mismatch in payload length
- `RESULT` for a test that is not running
- No `RESULT` arrives by the timeout after `RUN`

A protocol error is treated as a pytest error, and a reset is attempted if possible.

### 12.3 reset

`arduino_test.reset()` should be able to execute in the following order.

1. protocol `RESET_STATE`
2. serial / board reset if available
3. re-synchronization if necessary

How far this can be implemented depends on the existing `pytest-embedded` / serial layer.

---

## 13. Proposed pytest options

Initial candidates:

```text
--arduino-test-timeout=SECONDS
--arduino-test-missing-config=skip|error
--arduino-test-artifact-dir=PATH  # default: ardutest
```

Future candidates:

```text
--arduino-test-show-log
--arduino-test-collect
```

The options use names that do not conflict with the existing `arduino-cli` options.

---

## 14. Proposed Implementation Modules

```text
src/pytest_embedded_arduino_cli/
  ardutest.py
  ardutest_protocol.py
```

### 14.1 `ardutest_protocol.py`

- Command generation
- event parser
- payload reader
- protocol error definitions

### 14.2 `ardutest.py`

- The substance of the `arduino_test` fixture
- metadata / result dataclasses
- capability / config evaluation
- run lifecycle
- artifact saving

`plugin.py` holds only the fixture registration and option registration, and the detailed logic is separated into the modules above.

---

## 15. Test Strategy

### 15.1 unit test

- protocol parser
- command generation
- payload length handling
- capability env var normalization
- config env var normalization
- skip determination by requirement
- result aggregation
- artifact filename validation

### 15.2 integration test

At the initial stage, without real serial, the following are verified using a fake DUT / fake stream.

- The standard flow of `HELLO` / `LIST` / `RUN`
- Reflecting a failed result into a pytest failure
- Reflecting a missing config into skipped
- artifact saving

Real-hardware examples will be added under `examples/` at a later stage.

---

## 16. Open Issues

- Whether multiple values with the same metric name should be a list or the last value
- The default value of the artifact root
- Whether a protocol error should be expressed as a pytest error or a failure
- Whether the pytest result should be pass or skip when `arduino_test.run()` results in only skipped
- Whether to implement pytest item splitting in the future
