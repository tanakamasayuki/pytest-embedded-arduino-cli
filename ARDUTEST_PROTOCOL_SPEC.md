# ArduTest Communication Protocol Specification (Draft)

[日本語版 (Japanese)](ARDUTEST_PROTOCOL_SPEC.ja.md)

## 1. Overview

This specification defines the communication protocol used by the Arduino-side library `ArduTest` and the `pytest-embedded-arduino-cli`-side fixture `arduino_test` to control on-device tests over a `Stream`-compatible communication channel.

The goals of this specification are as follows.

- Allow the test list, requirements, and required config to be obtained during initial synchronization
- Allow the `arduino_test` side to determine the execution plan and instruct the Arduino side to run a single test
- Allow logs, metrics, artifacts, assertion failures, and final results to be collected mechanically
- Keep the format simple enough to be implementable even on an Arduino Uno

This specification describes the protocol as implemented by the shipped [ArduTest](https://github.com/tanakamasayuki/ArduTest) Arduino library (the device side) and the `arduino_test` fixture in this package (the host side). The ArduTest library is the canonical implementation of the device side; when the device behavior and this document disagree, the library is authoritative.

---

## 2. Design Policy

### 2.1 Basic Policy

- The communication channel assumes the Arduino `Stream`
- A one-message-per-line text protocol is the foundation
- Large bodies or bodies containing newlines are handled as length-prefixed payloads
- Keep the Arduino-side receive buffer small
- The pytest side parses strictly and turns invalid input into clear errors
- Retain enough readability for a human to read it in a serial monitor

### 2.2 Non-Goals

- A fast binary RPC
- Sending and receiving arbitrary JSON objects
- Complex capability evaluation on the Arduino side
- Compatibility with generic clients other than pytest

---

## 3. Terminology

- host: the PC that runs pytest
- device: the Arduino board on which ArduTest runs
- command: a control message sent from host to device
- event: a notification message sent from device to host
- payload: arbitrary-length data that follows the end of a message
- protocol version: the version representing the compatibility of the ArduTest communication specification

---

## 4. Communication Format

### 4.1 Line Format

A normal message is a single line of ASCII-compatible text.

```text
AT <direction> <type> [fields...]\n
```

- `AT` is the fixed prefix of the ArduTest protocol
- `<direction>` is `>` for host to device and `<` for device to host
- `<type>` is the uppercase message type
- `fields` are whitespace-separated
- The newline is `\n` by default, and the receiving side also accepts `\r\n`

Example:

```text
AT > HELLO 1
AT < HELLO 1 ArduTest 0.2.2
```

### 4.2 field encoding

`fields` have the following constraints.

- A string consisting of ASCII printable characters that contains no whitespace
- Test names, requirement names, config names, and metric names are recommended to match `[A-Za-z0-9_.:-]+`
- Values containing whitespace, newlines, or arbitrary text are sent as a payload

### 4.3 payload Format

A body containing newlines or whitespace is sent by including a byte length in the header line, followed immediately by the payload.

```text
AT < LOG <test-name> <length>\n
<payload bytes>
```

No additional terminator character is appended after the payload. When needed, the sender may follow the payload immediately with the next `AT ...\n`.

The receiving side reads only the `<length>` bytes from the header as the payload.

The interpretation of the payload is defined per message type. `LOG`, `ERROR`, `FAIL`, and `ARTIFACT_TEXT` are treated as UTF-8 text. `ARTIFACT_BINARY` is treated as raw binary bytes and is not subjected to text encoding such as Base64.

### 4.4 Numbers

- Integers use decimal notation
- Floating-point numbers use decimal notation equivalent to `Stream.print(value, digits)`
- The device sends only numeric metric values. On the host side, a metric value is converted to an integer or a float when possible, and otherwise kept as a string (it is not treated as a protocol error)

---

## 5. Version and Compatibility

### 5.1 protocol version

The initial protocol version is `1`.

After connecting, the host sends the protocol version it supports.

```text
AT > HELLO 1
```

The device returns the protocol version it uses, the library name, and the library version.

```text
AT < HELLO 1 ArduTest 0.2.2
```

If the host receives a protocol version it does not support, it aborts the tests.

### 5.2 Library Version

The library version represents the release version of the Arduino library. It is handled independently of the protocol version.

---

## 6. Overall Flow

### 6.1 Standard Flow

```text
1. pytest runs arduino-cli compile / upload
2. pytest opens the serial connection
3. pytest performs a reset / startup wait if needed
4. host -> device: HELLO
5. host -> device: LIST
6. device -> host: TEST / REQUIRE / REQUIRE_CONFIG / END_LIST
7. pytest evaluates capabilities and config
8. host -> device: SET_CONFIG
9. host -> device: RUN
10. device -> host: RUNNING / LOG / METRIC / ARTIFACT_TEXT / FAIL / RESULT
11. pytest reflects this into the pytest result, log, artifact, and metric
```

### 6.2 Handling of skip

skip is, in principle, decided on the host side.

- If a requirement is not satisfied, the host does not send `RUN` to that test and marks it as skipped in pytest
- When required config is missing, it is likewise treated as skipped or error on the host side
- The device does not send a `SKIP` result in the initial core

### 6.3 Handling of timeout

timeout is the responsibility of the host side.

- The device does not autonomously decide on a test timeout
- The host monitors the time from receiving `RUNNING` to receiving `RESULT`
- On timeout, the host treats it as an error in pytest and resets if necessary

---

## 7. Commands from host to device

### 7.1 HELLO

Confirms the protocol version.

```text
AT > HELLO <protocol-version>
```

### 7.2 LIST

Requests the sending of the test list and metadata.

```text
AT > LIST
```

The device sends `TEST`, `REQUIRE`, and `REQUIRE_CONFIG`, and then sends `END_LIST`.

### 7.3 SET_CONFIG

Passes a config value to the device.

```text
AT > SET_CONFIG <name> <length>\n
<payload bytes>
```

- `<name>` is the config name
- The payload is the config value
- If the same `<name>` is sent multiple times, the last one wins

### 7.4 CLEAR_CONFIG

Clears the config held on the device side.

```text
AT > CLEAR_CONFIG
```

This is used to avoid state pollution when running multiple times without a reset.

### 7.5 RUN

Runs a single test.

```text
AT > RUN <test-name>
```

The device runs only the specified test and always sends `RESULT` at the end.

### 7.6 RUN_ALL

Runs all tests in registration order.

```text
AT > RUN_ALL
```

`RUN_ALL` is an auxiliary command intended for manual confirmation and smoke tests. In normal pytest operation, the host builds an execution plan after `LIST` and repeats `RUN`.

### 7.7 RESET_STATE

Initializes the execution state of ArduTest.

```text
AT > RESET_STATE
```

The device clears the current test and failure state and leaves protocol mode. It produces no reply. Config is retained; use `CLEAR_CONFIG` when config also needs to be discarded. Because the device leaves protocol mode, the host re-synchronizes with `HELLO` on the next operation. The host exposes this as `arduino_test.reset()`.

---

## 8. Events from device to host

### 8.1 HELLO

Returns the device's protocol version and library version.

```text
AT < HELLO <protocol-version> ArduTest <library-version>
```

### 8.2 READY

Notifies that the device is ready to accept commands.

```text
AT < READY
```

`READY` may be sent spontaneously at startup. The host may send `HELLO` without waiting for `READY`, but `READY` can be used for the startup wait immediately after connecting.

### 8.3 TEST

Notifies of a registered test.

```text
AT < TEST <test-name>
```

### 8.4 REQUIRE

Notifies of a test's capability requirement.

```text
AT < REQUIRE <test-name> <requirement-name>
```

### 8.5 REQUIRE_CONFIG

Notifies of a test's required config.

```text
AT < REQUIRE_CONFIG <test-name> <config-name>
```

### 8.6 END_LIST

Notifies of the end of the test list transmission.

```text
AT < END_LIST
```

### 8.7 RUNNING

Notifies of the start of a test.

```text
AT < RUNNING <test-name>
```

### 8.8 LOG

Notifies of a log.

```text
AT < LOG <test-name> <length>\n
<payload bytes>
```

For a log that is not produced during test execution, set `<test-name>` to `-`.

### 8.9 METRIC

Notifies of a numeric metric.

```text
AT < METRIC <test-name> <metric-name> <value>
```

### 8.10 ARTIFACT_TEXT

Notifies of a text artifact.

```text
AT < ARTIFACT_TEXT <test-name> <filename> <content-type> <length>\n
<payload bytes>
```

- `<filename>` is a relative path
- `<content-type>` is `text/plain` by default in the initial core
- The host rejects path traversal

### 8.11 ARTIFACT_BINARY

Notifies of a binary artifact. The payload is raw binary bytes rather than Base64.

```text
AT < ARTIFACT_BINARY <test-name> <filename> <content-type> <length>\n
<payload bytes>
```

- `<length>` is the byte count of the raw binary payload
- The host saves the payload to a file as-is without decoding it

### 8.12 FAIL

Notifies of an assertion failure.

```text
AT < FAIL <test-name> <file> <line> <length>\n
<payload bytes>
```

Both plain assertion failures and equality assertion failures use the same `FAIL` event (there is no separate `FAIL_EQ`). The payload is one of:

- a failed expression (e.g. from `ASSERT_TRUE` / `ASSERT_FALSE` / `ASSERT_NE`)
- an equality comparison from `ASSERT_EQ`, formatted as `<expectedExpr>=<expected> <actualExpr>=<actual>`
- a supplementary message

### 8.13 RESULT

Notifies of the final result of a test.

```text
AT < RESULT <test-name> <status>
```

`<status>` is one of the following.

- `passed`
- `failed`
- `error`

In the initial core, `skipped` is a host-side result and the device does not send it.

### 8.14 ERROR

Notifies of a protocol error or an unexecutable state.

```text
AT < ERROR <code> <length>\n
<payload bytes>
```

The payload is a short human-readable message whose meaning depends on the code. The codes emitted by the device are:

| `<code>` | payload message | meaning |
| --- | --- | --- |
| `unknown_command` | the offending line, or `line_too_long` | an unrecognized command, or a command line longer than the receive buffer |
| `unknown_test` | the test name | `RUN` referenced a test that is not registered |
| `duplicate_test` | the duplicate test name | two registered tests share the same name (reported during `LIST`) |
| `invalid_config` | `missing_length` / `invalid_name` / `invalid_length` / `value_too_large` / `payload_timeout` / `store_full` | `SET_CONFIG` was malformed or the config store limit was exceeded |
| `internal_error` | (implementation-defined) | fallback when no specific code applies |

---

## 9. Test Metadata Registration Model

### 9.1 Requirements

So that the host can make a skip decision before execution, the device must be able to send each test's requirements and required config in the `LIST` response.

### 9.2 Initial API Proposal

A scheme that calls `REQUIRE()` inside a test function cannot be obtained as pre-execution metadata. Therefore, one of the following is adopted.

Proposal A:

```cpp
TEST_CASE(test_wifi) {
  ASSERT_TRUE(true);
}

ARDUTEST_REQUIRE(test_wifi, "network");
ARDUTEST_REQUIRE_CONFIG(test_wifi, "ssid");
```

Proposal B:

```cpp
TEST_CASE_WITH_REQUIREMENTS(test_wifi, "network", "ssid") {
  ASSERT_TRUE(true);
}
```

Proposal A was adopted. The ArduTest library ships `ARDUTEST_REQUIRE(test, "name")` and `ARDUTEST_REQUIRE_CONFIG(test, "name")`, and the device reports them as `REQUIRE` / `REQUIRE_CONFIG` events during `LIST`.

### 9.3 Runtime requirement

Cases where an environment shortage is discovered during execution are treated as `error` rather than an assertion failure, or are handled by a future explicit skip API. The initial core leans toward pre-execution metadata.

---

## 10. config Model

### 10.1 Sources

The host collects config from the following and sends it to the device.

- The fixture API
- Environment variables

The specific priority order is defined in the `pytest-embedded-arduino-cli`-side specification.

### 10.2 Device-side Retention

In the initial core, the device-side config is a key/value store with a small fixed upper limit.

Recommended initial values:

- Maximum count: 4
- Maximum key length: 31 bytes
- Maximum value length: 48 bytes

These match the default compile-time defines of the ArduTest Arduino library.
The upper limits can be changed on the Arduino side as needed, but be careful of RAM usage on low-capacity boards.

If an upper limit is exceeded, the device returns `ERROR invalid_config`.

### 10.3 Missing Required config

If config declared with `REQUIRE_CONFIG` does not exist on the host, the host marks that test as skipped in principle. However, room is left for users to configure it as an error.

---

## 11. capability Model

### 11.1 requirement Names

requirement names are declared by the Arduino side as arbitrary strings. The semantic interpretation is performed on the host side.

Example:

```text
network
wifi
measurement.current
sensor.temperature
```

### 11.2 capability Provision

The host side decides whether each requirement is satisfied based on the following.

- Environment variables
- fixture / plugin extensions

The initial proposal supports the fixture API and the environment variable `ARDUINO_TEST_CAP_<name>`. `.` and `-` are normalized to `_`, and matching is case-insensitive.

---

## 12. Artifact Storage

### 12.1 Storage Location

The host saves artifacts to the artifact directory resolved on the pytest side.

Recommended layout:

```text
<artifact-dir>/
  <test-name>/
    <filename>
```

The storage location option, the default value, directory creation, and deletion on clean are defined in [`ARDUTEST_PYTEST_SPEC.md`](ARDUTEST_PYTEST_SPEC.md).

### 12.2 filename Constraints

The host rejects the following filenames.

- Absolute paths
- Paths containing `..`
- An empty string
- Paths containing control characters that depend on the device or OS

---

## 13. pytest fixture API Proposal

The initial `arduino_test` fixture has the following API.

```python
def test_board(arduino_test):
    arduino_test.run()
```

Assumed API:

```python
arduino_test.list_tests()
arduino_test.run()
arduino_test.run("test_name")
arduino_test.reset()
arduino_test.artifacts
arduino_test.metrics
```

- `run()` runs all executable tests and reflects any failures as pytest failures
- `run("test_name")` runs only a single test
- skipped is reflected into the pytest skip / report
- metrics and artifacts are retained in a form that can be attached to the test report

---

## 14. Errors and Recovery

### 14.1 protocol error

The host treats the following as protocol errors.

- An unknown message type
- An incorrect number of fields
- A mismatch between the payload length and the actual data length
- A timeout of `RESULT` in response to `RUN`
- Receiving an event with a test name different from the running test

### 14.2 reset

After a communication interruption, timeout, or protocol error, the host resets as needed. The specific reset method is managed by the `pytest-embedded-arduino-cli` side.

---

## 15. Open Issues

- Whether to allow `skipped` as a device result
- Whether to fix the payload character encoding to UTF-8 or to define it only as binary-safe
- Whether to include artifact split transmission
- Whether to include metric units and tags in the protocol
