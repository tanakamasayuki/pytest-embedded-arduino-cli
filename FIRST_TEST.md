# Write Your First Test

[日本語](FIRST_TEST.ja.md)

This page creates a first test with one physical board and runs compile, upload, and serial communication end to end. Use the [README Quick Start](README.md#quick-start) if you only need the commands. This page explains what each file does and how pytest decides pass or fail.

If you do not have a board, start at [Try it without hardware](#try-it-without-hardware). A host core is a PC-side substitute, however, so physical hardware remains the standard onboarding path for this plugin.

## 1. Check the prerequisites

Verify that these commands are available:

```bash
arduino-cli version
uv --version
```

This example uses an Arduino Uno. Do not preinstall its board core into the environment. The `sketch.yaml` below declares the platform and version for Arduino CLI to resolve. An ESP32 follows the same route through the `esp32` profile.

A stale local package index may not know about a newer core version declared in `sketch.yaml`, even after that version has been published. Refresh the index before the first run, after updating a core version, or when Arduino CLI reports that the version cannot be found:

```bash
arduino-cli core update-index
```

For an ESP32, select the `esp32` profile below and the port for your board.

## 2. Create the Python workspace

Putting Python dependencies, a virtual environment, and pytest settings directly in the Arduino project root makes the two environments hard to distinguish. This guide therefore recommends a `tests/` directory that contains the Python workspace and test sketches together.

Run these commands at the root of an existing Arduino project:

```bash
mkdir tests
cd tests
uv init
uv add pytest-embedded-arduino-cli
```

`tests/` is now the Python-side workspace. The plugin, `.venv`, `uv.lock`, and pytest settings stay separate from the Arduino project itself.

## 3. Create the Arduino sketch

Continue from inside `tests/` and let Arduino CLI create the sketch:

```bash
arduino-cli sketch new hello
cd hello
touch sketch.yaml
touch test_hello.py
```

`arduino-cli sketch new hello` creates `hello/hello.ino` in the same shape as an Arduino IDE project. Add the plugin's `sketch.yaml` and pytest's `test_hello.py` beside it.

The relevant files now have this layout:

```text
tests/
  pyproject.toml
  hello/
    hello.ino
    sketch.yaml
    test_hello.py
```

Use the same layout as an Arduino IDE project: one primary `.ino` in the sketch directory, supporting code in `.h` / `.cpp` files, and the test file alongside them.

## 4. Write the sketch and profile

Replace the generated `hello.ino` with a sketch that replies with `PONG` when pytest sends `ping`.

```cpp
void setup()
{
  Serial.begin(115200);
}

void loop()
{
  if (Serial.available() == 0)
  {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line == "ping")
  {
    Serial.println("PONG");
  }
}
```

Write the board profiles in `sketch.yaml` in the same directory:

```yaml
profiles:
  uno:
    fqbn: arduino:avr:uno
    platforms:
      - platform: arduino:avr (1.8.8)

  esp32:
    fqbn: esp32:esp32:esp32
    platforms:
      - platform: esp32:esp32 (3.3.11)
        platform_index_url: https://espressif.github.io/arduino-esp32/package_esp32_index.json

default_profile: uno
```

In a real project, adjust the FQBN and core version to match the boards you support.

### Always specify the core version

Write `platform` as a core name and version, such as `arduino:avr (1.8.8)`. **Never omit the version.**

Without a version, Arduino CLI uses whichever core is already installed in that environment. `sketch.yaml` then cannot identify the version that produced the build, and the build fails if the environment has no copy of that core. Pinning the version lets Arduino CLI resolve the declared release and reproduces the same conditions on another machine or in CI.

`platform_index_url` is the Board Manager URL used by the Arduino IDE. Add it to the profile when a core needs an additional Board Manager URL and is not available from Arduino CLI's standard index. The ESP32 profile above is an example.

Choose the pinned version according to the project's purpose:

- **Projects that distribute built binaries:** pin the version used for production builds so tests and distributed binaries use the same conditions.
- **Projects that distribute source files:** users are likely to build in newer environments, so track recent core releases where practical. Run the tests before updating the supported version.

Pinning a version does not mean keeping an old version forever. Update the pinned value deliberately according to the project's policy.

## 5. Write the pytest test

Write the host-side actions and pass/fail decision in `test_hello.py` in the same directory.

By default, pytest finds Python files whose names start with `test_`, then runs functions inside them whose names also start with `test_`. That is why the file is `test_hello.py` and the function is `test_ping`. You do not write a `main()` or call the function yourself.

The `dut` argument is a fixture provided by this plugin and pytest-embedded. You do not construct the DUT object. Before the test runs, pytest compiles and uploads the sketch with the selected profile, connects to the serial port, and passes the connected DUT through this argument.

### Do not test startup serial traffic as if it were immediately reliable

Some boards cannot receive serial traffic immediately after startup. Upload or opening the serial port may already be complete while the board is still resetting, reconnecting USB serial, running its bootloader, or initializing the sketch. In other words, **being able to open the serial port does not mean that the sketch is ready to exchange text.**

Text sent by the host during this interval can be lost before it reaches the sketch. Conversely, a message printed only once by the sketch at startup can be missed if the host has not connected in time. A test can therefore fail even when the sketch is healthy if it assumes any of these one-shot startup exchanges:

- the host sends a command once and waits for its response;
- the test waits for a startup message printed only once from `setup()`;
- the test uses a short fixed delay despite startup time varying by board.

This example avoids those races with a PING/PONG readiness handshake. The host repeatedly sends `ping` at a short interval. Once the sketch is actually able to receive it, the sketch returns `PONG`, which marks communication as ready. The test does not depend on any particular startup attempt being delivered and passes only after bidirectional communication has worked.

```python
import time

import pexpect
import pytest


STARTUP_TIMEOUT = 20.0
PROBE_INTERVAL = 0.5


def test_ping(dut):
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        dut.write("ping\n")
        try:
            dut.expect_exact("PONG", timeout=min(PROBE_INTERVAL, remaining))
            return
        except pexpect.TIMEOUT:
            continue
    pytest.fail(f"device did not answer PONG within {STARTUP_TIMEOUT} seconds")
```

If the first `ping` does not reach the board, there is no corresponding `PONG`, so the first `dut.expect_exact(...)` times out. That is expected while the board is starting. Each attempt is limited to the 0.5-second `PROBE_INTERVAL`, and the following `except` catches the timeout, so the whole pytest test does not fail and can send another `ping`.

The retries have a separate 20-second `STARTUP_TIMEOUT`. It serves two purposes: tolerate normal startup variation and still fail in finite time when the device has actually stopped responding.

Too short a value rejects a healthy board in a slow environment. Too long a value delays every real failure, including a broken device or wiring error. Most boards respond within a few seconds, and about 20 seconds is a useful upper-end starting point even for slower environments. Still, **measure the slowest healthy environment, add reasonable margin, and choose a duration you can still afford to wait on failure.** Twenty seconds is the initial value for this example, not a universal answer.

If startup time itself is a performance requirement, test it separately. First establish that the device eventually starts with a forgiving functional timeout, then assert measured timing in a dedicated test. A strict functional timeout cannot distinguish a stopped device from a mere performance regression.

Each part has a specific role:

| Code | Role |
| --- | --- |
| `import pexpect` | Provides `pexpect.TIMEOUT`, which indicates that serial output did not arrive in time. It is already a plugin dependency. |
| `import pytest` | Provides `pytest.fail(...)` so the final failure includes a useful reason. |
| `import time` | Provides `time.monotonic()`, which measures the deadline without being affected by system clock changes. |
| `STARTUP_TIMEOUT` | Sets the overall startup deadline and should be adjusted for the project and environment. |
| `PROBE_INTERVAL` | Sets one response wait and the interval between repeated queries. |
| `def test_ping(dut)` | Defines a test pytest collects and receives the connected DUT fixture. |
| `dut.write("ping\n")` | Sends text from the host to the device. The newline is required because the sketch reads through `readStringUntil('\n')`. |
| `dut.expect_exact(...)` | Waits for an exact, case-sensitive `PONG` for the shorter of `PROBE_INTERVAL` and the remaining overall time. |
| `except pexpect.TIMEOUT` | Catches one response timeout, preventing the whole test from failing and continuing to send `ping` until the deadline. |
| `return` | Ends the function after observing `PONG`. A test that returns without an exception or `pytest.fail` passes. |
| `pytest.fail(...)` | Fails with an explicit reason and duration when the overall deadline expires. |

At runtime:

1. pytest discovers `test_hello.py` and `test_ping`.
2. The plugin compiles and uploads using the profile in `sketch.yaml`.
3. It connects to the serial port and supplies `dut` to the function.
4. The test sends `ping` and waits 0.5 seconds for `PONG`.
5. It resends after an unanswered attempt and passes as soon as a response arrives.
6. It fails with a message if no response arrives before `STARTUP_TIMEOUT`.

A fixed delay such as `time.sleep(3)` is too short in a slow environment and wasted time in a fast one. Querying until the device actually answers tolerates changes in startup time.

Here `expect_exact` makes “the device emitted this text” the pass condition. [Testing Basics](TESTING_BASICS.md) and [Advanced Testing](TESTING_ADVANCED.md#traps-in-expect) cover comparisons, multi-line exchanges, and capturing values with regular expressions.

## 6. Find the port and run

Return to the Python workspace, then use Arduino CLI to list connected boards and their ports:

```bash
cd ..
arduino-cli board list
```

For an Uno:

```bash
uv run pytest hello --profile=uno --port=/dev/ttyACM0
```

For an ESP32:

```bash
uv run pytest hello --profile=esp32 --port=/dev/ttyUSB0
```

On Windows, replace the port with a name such as `COM3`. A successful run ends with `1 passed`.

See [Testing Basics: Keeping port settings in `.env`](TESTING_BASICS.md#keeping-port-settings-in-env) to avoid passing the port every time.

## If it does not work

Start by rerunning with `-s` and `-v`; together they make it easier to see which stage has stopped progressing.

```bash
uv run pytest hello --profile=uno --port=/dev/ttyACM0 -s -v
```

- `-s` shows received serial output in the console while the test is running. Serial logging continues at the same time and is still saved to `dut.log`. Use it to see immediately how far the sketch starts and what text the board actually emits.
- `-v` shows collected test names and the `arduino-cli compile` / `arduino-cli upload` commands executed by the plugin. Use `-vv` to also see details such as `cwd`, sketch directory, build path, profile, and port.

The options have different roles and can be combined. Use `-s` to watch serial communication live and `-v` or `-vv` for compile, upload, and configuration resolution. Serial logs are collected even without `-s`, so it is reasonable to enable the noisier live display only while diagnosing a problem.

On Linux, a saved log is typically under `/tmp/pytest-embedded/<run timestamp>/<test name>/dut.log`. The root varies with the operating system and temporary-directory configuration. See [FAQ: I want to watch serial output during the run and inspect it afterward](TESTING_FAQ.md#i-want-to-watch-serial-output-during-the-run-and-inspect-it-afterward) for the distinction from `-s` and for choosing a fixed log directory.

- `arduino-cli` is not found: install Arduino CLI and add it to `PATH`.
- A platform or version is not found: refresh the package index and check the platform name, index URL, and version in `sketch.yaml`. Do not work around it by manually installing the core into the environment.
- Upload fails: check the port with `arduino-cli board list` and close other programs using it, such as the Arduino IDE serial monitor.
- Output is garbled: match the baud rate to `Serial.begin(115200)`. The default is 115200.
- For other symptoms, search the [FAQ](TESTING_FAQ.md).

## Try it without hardware

A host core builds the sketch as a PC executable and connects over a TCP socket instead of a serial port. The host machine must already provide a `gcc` / `g++`-compatible C/C++ toolchain, and the test cannot cover hardware-specific behavior. The host-core package does not install a compiler or linker, so install these through the operating system first.

On Debian or Ubuntu Linux, install the toolchain as follows if it is not already present. See [host-arduino-core: Prerequisites](https://github.com/tanakamasayuki/host-arduino-core/blob/main/README.md#prerequisites) for other operating systems and details.

```bash
sudo apt update
sudo apt install build-essential
gcc --version
g++ --version
```

The sample belongs to `examples/09_host_arduino_core` in the `pytest-embedded-arduino-cli` repository, rather than to the Arduino project created on this page. To make a fresh clone under `/tmp` and try it on Linux, run:

```bash
cd /tmp
git clone https://github.com/tanakamasayuki/pytest-embedded-arduino-cli.git
cd pytest-embedded-arduino-cli
uv run pytest examples/09_host_arduino_core --profile=host -s -v
```

There is no need to run `uv sync` first because `uv run` prepares the Python environment from the repository configuration. If you already cloned the repository elsewhere, replace the first two commands by changing to that repository root, then run the same `uv run pytest ...` command.

See [`examples/09_host_arduino_core`](examples/09_host_arduino_core/README.md) for its configuration and limitations.

## Where to go next

- [Testing Basics](TESTING_BASICS.md): module, test, physical hardware, host core, and peer concepts
- [examples](examples/README.md): runnable samples organized by purpose
- [README](README.md): options and configuration reference
- [FAQ](TESTING_FAQ.md): diagnosing errors and unstable tests
