# Testing Basics

[日本語](TESTING_BASICS.ja.md)

A guide for writing your first tests with this plugin. It starts from what a test is, so you can read it without knowing pytest.

## What a test is

A test is a way to let a machine check, the same way every time, what you used to check by hand.

Developing for a microcontroller usually means flashing a sketch, opening a serial monitor, reading the output, typing a command and watching the reaction. A test is that procedure written down as code. Write it once and the same check runs automatically every time you change something.

With this plugin, a test comes down to one sentence.

**Flash a sketch to the board, exchange messages over serial, and check that the expected output appears.**

## Terms

Here are the words this guide uses.

| Word | Meaning |
| --- | --- |
| host | The PC that runs the tests. The side pytest runs on. |
| device | The microcontroller board being tested. Also called the board. |
| DUT | Short for Device Under Test: the device being tested. This is the `dut` argument of a test function. |
| peer | A device the DUT talks to. There can be as many as you need, not just one. |
| sketch | An Arduino program, the `.ino` file. |
| profile | The settings for which board to build for and how. Written in `sketch.yaml`. |
| host core | A board core that builds the sketch for the host and runs it as a PC program, with no microcontroller involved. |

Host and device come up throughout. **The host side** means the PC pytest runs on, and comes up when deciding which side judges pass or fail. **The device side** is the microcontroller board under test.

Separately you will see the term **host core**. That is a kind of board core which builds the sketch as a PC program instead of for a microcontroller, and runs it on the PC. "Deciding on the host" and "running on a host core" are different things, so do not conflate them.

## How it works

When you run `pytest`, this happens in order.

1. pytest collects the functions whose names start with `test_`. Those are the tests that run.
2. The plugin compiles the `.ino` in the same directory as that test file, using `arduino-cli`.
3. It uploads to the board. This resets the board, and the sketch starts running.
4. It opens the serial port.
5. Your test function runs. It sends with `dut.write(...)` and waits with `dut.expect_exact(...)`.
6. If the expected text arrives, the test moves on. If it does not, the test fails on a timeout.
7. The serial port is closed.

The smallest possible pairing is this. A sketch file and a test file go together.

```cpp
// hello.ino
void setup()
{
  Serial.begin(115200);
  delay(1000);
  Serial.println("hello from arduino");
}

void loop()
{
}
```

```python
# test_hello.py
def test_hello(dut):
    dut.expect_exact("hello from arduino")
```

The sketch prints one line with `Serial.println` and the test waits for it with `dut.expect_exact`. That pairing is the basic shape.

Match the speed in `Serial.begin(115200)` with the test side. This plugin defaults to 115200, and `--baud` changes it. A mismatch delivers garbled lines.

Naming `dut` as an argument of the test function is what makes steps 2 through 4 happen.

Sending first and checking the reply looks the same. The sketch reads one line at a time and treats it as a command.

```cpp
// echo.ino
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

```python
# test_echo.py
def test_echo(dut):
    dut.write("ping\n")
    dut.expect_exact("PONG")
```

The sketch reads the `ping` that `dut.write` sent, answers `PONG`, and the test waits for it. Every later example uses this shape.

The mix of cases is deliberate. **Commands sent from the host are lower case, and result lines printed by the device are upper case.** It is not a rule, but it makes the direction of a line obvious at a glance in a log, so this guide keeps to it throughout.

### There are two places to decide pass or fail

- **Decide on the host.** The test code checks the text it received. The sketch only has to print values. Every example so far is this.
- **Decide on the device.** The judgement happens inside the sketch, which prints only the result. This suits cases where you want to inspect values inside the board directly.

Written plainly, deciding on the device looks like this.

```cpp
  int sum = add(2, 3);
  if (sum == 5)
  {
    Serial.println("ADD_PASS");
  }
  else
  {
    Serial.print("ADD_FAIL sum=");
    Serial.println(sum);
  }
```

```python
def test_add(dut):
    dut.expect_exact("ADD_PASS")
```

The judgement lives in the sketch, so the test only waits for the result line.

Libraries such as Unity and ArduTest are a tidied-up version of this. Here is how they work.

1. The sketch runs several checks itself.
2. It prints the result of each check, plus how many passed and how many failed.
3. One line on the test side reads that output: `dut.expect_unity_test_output()` for Unity, `arduino_test.run()` for ArduTest.
4. **If even one check failed, that pytest test fails.** The error names the checks that failed.

```python
def test_unity(dut):
    dut.expect_unity_test_output(timeout=60)   # fails here if any check failed
```

So from pytest's point of view it is one test, and inside it any number of device-side checks run. Adding a check does not mean editing the test file. This is the shape that pairs well with "put it all in one larger test" later on.

With Unity each check is also recorded in the junit report, so `--junitxml` keeps per-check results.

Either is fine, and you can mix them.

## What only real hardware can tell you

With a host core you can run the sketch as a PC program. It is fast and needs no board attached, but there is a limit to what it proves.

| Subject | Can a host core tell you? |
| --- | --- |
| Pure logic such as computation, parsing, state machines | Yes |
| The shape of a protocol exchanged over serial | Yes |
| Peripherals such as GPIO, I2C, SPI | No |
| Real-time timing, interrupts | No |
| Persistence in non-volatile storage | No |
| Board-specific APIs, Wi-Fi, BLE, USB | No |

Running on a host core is not a substitute for testing on hardware. Results can also shift with the PC's OS, the gcc version, and how the host core implements `Serial`. Treat it as a way to iterate on logic quickly.

### The idea of a unit test

A unit test checks one part at a time, in isolation. It targets a single function or class and keeps the surroundings out of it. A test that runs the whole thing on hardware, by contrast, looks at how the parts combine. Both have a role.

| | One part (unit test) | Combined (hardware test) |
| --- | --- | --- |
| Subject | A function or a class | The whole sketch plus the hardware |
| Speed | Fast | Slow; flashing alone takes time |
| What you need | Nothing; a host core is enough | A board, which has to be shared |
| When it fails | The cause is in a narrow place | The cause could be anywhere |

Here is the rule of thumb for dividing them. **Anything determined by its inputs and outputs, such as computation, parsing and state machines, belongs in unit tests on a host core.** Leave only what hardware alone can tell you, such as peripherals, timing and radio, for hardware tests. Hardware tests are slow and the boards are limited, so the more you narrow down what they check, the faster the whole suite gets.

On a microcontroller the parts can be hard to isolate, because code that touches hardware directly sits mixed in with code that computes and decides. Separate those two and the latter runs on a host core. Thinking about testability doubles as a design guideline.

Unit tests are not only for a host core, either. Checking individual functions inside the board with Unity or ArduTest is also a unit test, just one that runs on hardware. Parts that depend on peripherals end up in that form.

**You can choose where to run them.** A host core has two advantages: nothing is uploaded, so it is fast, and no board is needed. In exchange you have to add the host core platform and have an environment on the PC that can build C++.

**Running your unit tests only on hardware is perfectly fine.** Flashing costs time, but the environment stays exactly what ordinary Arduino development already needs. Starting on hardware, then adding a host core later once the waiting starts to bother you, is a perfectly reasonable order.

## Directory layout

In an Arduino project the library and the sketches live at the root. Mixing Python tooling in there makes a mess, so the recommended arrangement is to **keep everything test-related under `tests/` and leave the root clean.**

```text
MyLibrary/                 <- the Arduino library root
  library.properties
  src/
  examples/
  tests/                   <- the root of the Python side
    pyproject.toml         <- dependencies and pytest settings
    uv.lock
    .env                   <- per-machine values such as the port; not committed
    .env.example           <- a template to share
    my_app/                <- one test application
      my_app.ino
      sketch.yaml
      test_my_app.py
```

Dependencies go in `tests/pyproject.toml`, so the Python virtual environment is created at `tests/.venv` and never mixes with the Arduino files.

**Commands are run from inside `tests/`.** The rest of this guide assumes that.

```bash
cd tests
uv run --env-file .env pytest my_app
```

As the tests grow, split what is under `tests/` by purpose.

```text
  tests/
    unit/                  <- tests that need no board; no .ino here
    suites/                <- hardware tests in the default run
      my_app/
        my_app.ino
        sketch.yaml
        test_my_app.py
    manual/                <- tests needing occasional equipment or a person
    sketch_support/        <- headers shared by the sketches
    conftest.py            <- only once you actually need one
```

The names are yours to choose. What matters is that **what runs by default is separated from what does not.**

Name test files after their sketch directory, as `test_<sketch name>.py`, so that they are **unique across the whole project**. Two files with the same name fail at collection time when someone runs everything. Set the default target in `pyproject.toml`.

```toml
[tool.pytest.ini_options]
testpaths = ["unit", "suites"]
```

```bash
cd tests
uv run --env-file .env pytest              # only what testpaths names
uv run --env-file .env pytest manual/      # name the occasional ones explicitly
```

## How many boards to use

What you can test depends on the board count. Starting with fewer is easier.

### Zero boards: run on a host core

With a host core, the sketch is built with the PC's gcc and launched as an executable on the PC. Instead of a serial port, it is reached over a TCP socket.

```yaml
# sketch.yaml
profiles:
  host:
    fqbn: lang-ship:host:host
    port: socket://localhost
    platforms:
      - platform: lang-ship:host (1.7.1)
        platform_index_url: https://tanakamasayuki.github.io/lang-ship-arduino-core/package_lang-ship_index.json

default_profile: host
```

This suits checking logic, and no board has to be shared.

**But a host core means one test per module.** Closing the connection ends the executable, so **a second test in the same module cannot connect**; measured, it is refused. `parametrize` fails for the same reason. To split, split the module. With no flashing to wait for and no board to share, adding a module costs comparatively little here.

**Being able to run in CI is a major benefit.** A CI service such as GitHub Actions cannot have a board attached, but a host core needs none, so it just runs. Even without a bench of your own, the logic unit tests get checked automatically on every change. For a public open-source repository the free tier covers it, so it costs nothing.

Hardware tests only run on your own bench or on a self-hosted runner you set up yourself. So the more you move onto a host core, the wider the range that gets checked automatically.

### One board: run on hardware

The basic setup, used for unit tests on real hardware.

```bash
pytest my_app --port=/dev/ttyUSB0
```

A way to avoid typing `--port` every time is covered after the peer sections.

Even with one board you can wire an output back to an input as a loopback and exercise both directions. Peripherals, timing and persistence, the things a host core cannot tell you, start here.

### Two boards: tests that need a partner

For tests that need someone to talk to, put a `peer_<name>/` directory inside the sketch directory.

```text
tests/
  my_app/
    my_app.ino
    sketch.yaml
    test_my_app.py
    peer_echo/
      peer_echo.ino
      sketch.yaml
```

Ask for `peers` in the test function and the peer is built, uploaded and connected too.

```python
def test_round_trip(dut, peers):
    echo = peers["echo"]
    dut.write("send\n")
    echo.expect_exact("RECEIVED")
```

You write two sketches. The primary sends to the peer over whatever transport you are testing when it receives `send`, and the peer prints `RECEIVED` when it gets something. Whether the transport is BLE, Wi-Fi or I2C, the test side looks the same.

BLE and Wi-Fi obviously need a partner, but many other tests are simply easier with two boards. You can read the other side's log directly, which tells you which side is at fault.

### Three or more boards: cluster-style tests

Just add more peer directories, with distinct names such as `peer_device` and `peer_device2`.

```text
    peer_device/
    peer_device2/
```

That lets you build setups like one Central connected to two Peripherals at once, or a relay in the middle.

More boards work the same way: add a peer directory and a port.

This guide assumes the boards you need are attached. In reality a bench mixes boards that are always connected with boards you attach only for the occasion. **If a peer's port cannot be resolved, the tests using that peer are skipped automatically.** They do not fail, so on a bench with fewer boards everything else still runs.

**That behaviour is for peers only.** When the primary DUT's port cannot be resolved, nothing is skipped and the run fails. The thing under test is missing, so it is treated as a configuration error.

Organizing tests that need equipment which is not always attached is covered in the [advanced guide](TESTING_ADVANCED.md).

## Keeping port settings in `.env`

Writing `--port` every time is tedious, and the value differs per machine. Put it in a `.env` file and you can leave it out.

```bash
# .env
TEST_SERIAL_PORT=/dev/ttyUSB0
```

```bash
uv run --env-file .env pytest my_app
```

`--env-file` is an option of `uv`, not of pytest, so it **goes before `pytest`**. Without `uv`, `export TEST_SERIAL_PORT=/dev/ttyUSB0` does the same.

A `.env` holds per-machine settings, so **do not commit it**. This repository lists it in `.gitignore`. To share the shape of it, add a `.env.example` with the values blanked out and have everyone copy it.

If you switch between boards, you can set one per profile. The variable name is the profile name upper-cased with `-` replaced by `_`.

```bash
# .env
TEST_SERIAL_PORT=/dev/ttyUSB0          # the default
TEST_SERIAL_PORT_ESP32=/dev/ttyUSB0    # used with --profile esp32
TEST_SERIAL_PORT_UNO=/dev/ttyACM0      # used with --profile uno
```

Peers have the same mechanism. For `peer_echo` it is `TEST_SERIAL_PORT_PEER_ECHO`.

```bash
# .env
TEST_SERIAL_PORT_PEER_ECHO=/dev/ttyUSB1
```

A `--port` on the command line wins over `.env`. So you can keep the usual value in `.env` and add `--port` only when trying a different board. The full precedence is in the [advanced guide](TESTING_ADVANCED.md).

## session, module, test

The rest of this guide matters once you have more than one test. Here is what pytest's three terms mean in this plugin.

| Term | Meaning | Role in this plugin |
| --- | --- | --- |
| session | One whole pytest run | Walks through several sketches in turn |
| module | One test file | The unit of sketch compile and upload |
| test | One `def test_...` function | The unit of opening and closing the serial connection |

A module is one test file. The `.ino` in the directory holding that file is the module's sketch.

The reverse also holds: **for a test file in a directory with no `.ino`, this plugin does nothing at all.** Nothing is compiled or uploaded, and it runs as plain pytest. Keep unit tests that need no board in a directory with no `.ino` in it.

```text
tests/
  unit/
    test_parser.py     <- no .ino here, so the plugin does nothing
  my_app/
    my_app.ino
    sketch.yaml
    test_my_app.py     <- a test in a sketch directory
```

One thing to watch. **Put a test in a directory that has an `.ino` and the sketch is compiled and uploaded, even if that test never asks for `dut`.** Compiling and uploading are module-level preparation, run independently of whether a test connects. Mixing board-free tests into a sketch directory adds waiting for nothing and ties up the board.

This is what happens at each level.

- **Session start**: pytest starts up and collects the tests to run.
- **Module start**: the sketch is compiled and uploaded to the board. **The upload resets the board.** For a physical board, the device lock is acquired.
- **Test start**: the serial port is opened. The plugin does not deliberately do anything to reset the board, but opening a port asserts DTR and RTS. **Whether that resets the board depends on the board's circuit.**
- **Test end**: the serial port is closed.
- **Module end**: the device lock is released.

**One caveat, though: whether an upload erases non-volatile storage depends on the board.** Settings, logs, pairing information. **In many cases it is not erased by default.** Where that holds, data a test wrote persists across modules and across runs, and that becomes **a place where "a module boundary is always clean" does not hold.**

There are two ways to deal with it, and which one fits depends on the situation.

- **Clear it from the sketch at the start of the test.** If the sketch can reach the storage, this works on any platform. It is the one to reach for when in doubt.
- **Erase before flashing.** Available where the platform offers a full-erase setting. **There is no unified way to write it, each platform spells it differently, and some platforms offer no full erase at all.** On ESP32, for example, it is offered as a modifier on the profile's `fqbn`.

```yaml
# one example, for ESP32. Other platforms spell it differently
profiles:
  esp32:
    fqbn: esp32:esp32:esp32:EraseFlash=all
```

Forgetting either is nasty. A failure that depends on a previous run **reproduces neither when run alone nor in reverse.**

One important conclusion follows. **The upload always resets the board. Whether the per-test connection resets it depends on the board.** On some boards the next test sees exactly what the previous test left behind; on others every connection resets it away. Boards that wire DTR and RTS straight to EN reset; boards with an auto-reset circuit in between, and native USB boards, usually do not.

So when you add a second test to the same module, the board state that test sees depends on the board's circuit. **Writing tests that depend on neither is the only safe approach.**

## As a rule, one test per module

**Use this shape unless you have a specific reason not to.** The difference is not a matter of taste; treat it as the default.

```text
tests/
  blink/
    blink.ino
    sketch.yaml
    test_blink.py      <- a single def test_blink(dut)
```

When you have more to verify, consider these three options before adding a test function.

1. **Put it all in one larger test.** If you send commands in sequence and check the replies, you can chain as many steps as you like inside a single test.
2. **Keep the sketch and add a module.** Put a second test file in the same sketch directory and each becomes its own module. **This is the one to reach for when you want to split while sharing the sketch.**
3. **Split the sketch itself.** For when the features are genuinely different and the sketch should differ too.

**Options 2 and 3 behave identically.** Both produce separate modules, so **the compile and the upload run each time, and the board is reset and starts clean on each one.** The only difference is whether the sketch is shared. It costs more than splitting tests, but state independence is guaranteed. "Splitting while keeping independence" below covers it in detail.

## When multiple tests are fine

Multiple tests are fine only when **every test passes when run on its own**. This is what stateless means.

**Some tests are naturally stateless and some are not.**

- **Naturally stateless: anything determined by its inputs and outputs.** Checking a computation or a parser, or sending one command and checking the reply. No device state is involved, so the result is the same whatever position it runs in. **This is the shape of a unit test.**
- **Not naturally stateless: anything that builds device state first.** Tests that connect, enumerate, or configure a peripheral. Left alone, they run on top of whatever the previous test left behind. Making them stateless means rebuilding the state yourself at the start.

**The first kind is safe to split; the second kind is where splitting causes trouble.** The second is exactly where one test per module pays off.

The first kind, the unit-test shape, is **cheaper to run on a host core**: no flashing and no hardware. But **a host core cannot split tests**, as noted above: a second test in the same module cannot connect. So **the place where they are cheapest to run is the place where they cannot be split.** For granularity there, check things in sequence inside one test, or add a module; adding a module is comparatively cheap on a host core.

Note also that the first kind can be done by sending the commands in sequence inside one larger test. Splitting is not required.

Beyond that, **decide whether to split by weighing the benefits against the costs.**

**Laid out, the benefits are smaller than they look.**

- **The name tells you where it broke.** But a merged test still prints the line that failed, and you read where it stopped either way. Having a name adds little beyond being easier to pick out of a result list. If per-check records are all you want, reporting from the device is more reliable.
- **You can run just one.** But to carve out a slow piece of verification, **splitting the module is the better fit**: put two test files in the same sketch directory and each gets its own upload, so the state is independent too.
- **One failure does not stop the rest from running.** This one is unique to splitting. On hardware, though, the board is often left in a bad state by the failure, so what follows may not be worth much.

**Costs**

- **Every test reconnects.** The upload happens once per module, so reconnecting is all that a test after the first adds. It is a small cost.
- **Every test needs its own setup and cleanup.** When that is heavy, the time multiplies by the number of tests. In a setup that stops and restarts radio or USB each time, this becomes most of the run.
- **The port is opened and closed once per test.** On some boards, opening it resets the board, which means **an unintended reset per test.** Where that happens the start-up runs every time and its cost is added too. And since it varies by board, **the same tests behave differently on different boards.**
- **It opens the door to order dependence.** You then have to check that none crept in.

**The rule of thumb.** Splitting is not expensive, but **it does not buy much either.** And on some boards you pay an unintended reset and a boot for every test you split off. **Take one test per module as the rule, and split only for one of the limited reasons.** When you want to split, first ask whether the sketch or the module can be split instead, or whether reporting from the device would do.

If you still split, two conditions apply: **the tests stay stateless**, and **per-test setup and cleanup are light**. What decides it is the time each extra test adds, not the count.

Some cases have no substitute, such as repeating with a value that varies on the host, or wanting a marker per case. They are collected under "When splitting really is required" in [Advanced Testing](TESTING_ADVANCED.md).

## The trap: depending on an earlier test breaks single runs

This section works against the sketch below. It counts every `send`, answers the count on `count?`, and resets to zero on `reset`.

```cpp
// counter.ino
int sent = 0;

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

  if (line == "reset")
  {
    sent = 0;
    Serial.println("RESET_OK");
  }
  else if (line == "send")
  {
    sent++;
    Serial.println("SENT");
  }
  else if (line == "count?")
  {
    Serial.print("COUNT ");
    Serial.println(sent);
  }
}
```

`sent` survives until the next upload resets it. That is the seed of the trap.

Here is what not to do.

```python
# Bad
def test_send_first(dut):
    dut.write("send\n")
    dut.expect_exact("SENT")


def test_count(dut):
    dut.write("count?\n")
    dut.expect_exact("COUNT 1")     # assumes test_send_first ran
```

Run `test_count` alone and the count is 0, so it fails. Reorder the tests and it fails. Let `test_send_first` fail and it fails. On a board that resets on every connection, it fails even when run in order. It is a bad example on any board.

Here it is fixed.

```python
# Good
def test_send(dut):
    dut.write("reset\n")
    dut.expect_exact("RESET_OK")
    dut.write("send\n")
    dut.expect_exact("SENT")


def test_count(dut):
    dut.write("reset\n")
    dut.expect_exact("RESET_OK")
    dut.write("send\n")
    dut.expect_exact("SENT")
    dut.write("count?\n")
    dut.expect_exact("COUNT 1")
```

Each test establishes the state it needs. Either one passes when run alone.

**There are two ways to check.**

One is to run the tests one at a time. If they all pass, they are stateless. This is also the criterion for being able to run a single test with `-k` or a node id.

```bash
pytest my_app/test_my_app.py::test_count
```

The other is to **run the module once with its tests reversed.** It costs one upload, so it is the practical everyday check. Order dependence usually shows up right here.

```bash
pytest $(pytest my_app --collect-only -q | grep '::' | tac)
```

What kinds of dependence arise, and how to fix each, is collected in "Building a clean test plan" in [Advanced Testing](TESTING_ADVANCED.md).

### Splitting while keeping independence

This is the second option listed earlier. Put two test files in the same sketch directory and each becomes its own module. The upload runs once per module, so the board is reset each time.

```text
tests/
  my_app/
    my_app.ino
    sketch.yaml
    test_quick.py      <- module 1, gets an upload
    test_slow.py       <- module 2, gets another upload
```

**Splitting the module runs both the compile and the upload again.** The compile can be faster than the first thanks to Arduino CLI's incremental build, but it is not free. In exchange, state independence is guaranteed. This is a good way to carve out a slow test.

## The device does not answer at the start of a test

Right after the upload the board is booting and running `setup()`. During that time it will not answer anything you send over serial. Library initialization, bringing up Wi-Fi or BLE, USB enumeration and so on all take time, and how long varies with the environment.

**Do not wait for a fixed amount of time.**

```python
# Bad
import time


def test_bad(dut):
    time.sleep(3)            # nothing guarantees 3 seconds is enough
    dut.write("ping\n")
    dut.expect_exact("PONG")
```

It fails where three seconds is not enough. It wastes three seconds every run where one would do.

Wait for **an actual reply** instead. There are two ways to do it and you can pick either.

### Method A: poll from pytest

Give the sketch one query command and keep sending it until a reply comes back.

```cpp
// polling.ino
void setup()
{
  Serial.begin(115200);
  delay(3000);                  // pretend initialization takes 3 seconds
}

void loop()
{
  if (Serial.available() == 0)
  {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();

  if (line == "?")
  {
    Serial.println("READY");
  }
  else if (line == "ping")
  {
    Serial.println("PONG");
  }
}
```

No flag is needed to record whether it is ready. **While initializing, `loop()` does not run, so nothing you send is read.** If your sketch brings up Wi-Fi or BLE inside `setup()`, that property does the work for you. If instead you advance initialization step by step inside `loop()`, you have to stop yourself from answering commands before you are ready.

```python
import pexpect
import pytest


def wait_ready(dut, attempts=20, interval=0.5):
    for _ in range(attempts):
        dut.write("?\n")
        try:
            dut.expect_exact("READY", timeout=interval)
            return
        except pexpect.TIMEOUT:
            continue
    pytest.fail("device did not become ready")


def test_with_polling(dut):
    wait_ready(dut)
    dut.write("ping\n")
    dut.expect_exact("PONG")
```

**Why resend, rather than send once and wait a long time?** Because bytes sent too early can be lost.

- On a native USB board, bytes sent before USB enumeration completes never arrive.
- On a board that resets when the port is opened, anything sent before that reset is gone.
- Bytes sent during initialization are read afterwards if they are still in the serial receive buffer, but nothing guarantees they are.

Send once and wait, and there is no recovery if that one attempt was lost. Keep resending and the next attempt after the device starts listening gets an answer. It works whenever the connection happens to open, which makes it reliable on real hardware.

### Method B: let the device announce it is ready

The sketch prints one line at the end of `setup()` and pytest waits for it.

```cpp
// announce.ino
void setup()
{
  Serial.begin(115200);
  delay(3000);                  // pretend initialization takes 3 seconds
  Serial.println("READY");
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

```python
def test_with_announcement(dut):
    dut.expect_exact("READY", timeout=10)
    dut.write("ping\n")
    dut.expect_exact("PONG")
```

There is less to write, but note one thing. pytest opens the serial port after the upload, so **a `READY` printed before that can be missed**.

This really happens. With two boards, the one that finishes flashing first boots and starts printing while the second is still being flashed. Where flashing takes minutes, all of the startup output has gone by before pytest connects. The symptom is that **one side's log is completely empty**. It is not a bug in the sketch, it is the timing of flashing and resetting.

With a host core over a socket the output is retained, so this is much less likely there.

If you use method B on real hardware, either have the sketch repeat `READY` or move to method A. For states that are announced once at the moment they happen, also let the sketch answer the current value on a query, so a test never has to wait for the announcement.

## Summary

- A test is the procedure you used to run by hand, written as code: flash the sketch, talk over serial, check the expected output.
- Running on a host core suits logic. Peripherals, timing, persistence and radio can only be checked on hardware.
- Zero, one, two, or three-plus boards each unlock different tests. Adding a peer is just adding a name.
- The upload is per module, the serial connection is per test. The upload always resets the board; whether a connection does depends on the board.
- **As a rule, one test per module.** Split only for one of the limited reasons. The benefits are small and the costs vary by board.
- If you do write several tests, every one of them must pass on its own, must not depend on an earlier test, and should pass in reverse order too.
- Wait for a reply, not for a fixed amount of time.

More advanced topics are in [Advanced Testing](TESTING_ADVANCED.md). Real, working projects are collected in [Example Projects](TESTING_EXAMPLES.md).
