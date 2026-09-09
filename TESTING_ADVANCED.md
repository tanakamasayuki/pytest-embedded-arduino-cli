# Advanced Testing

[日本語](TESTING_ADVANCED.ja.md)

A follow-on from [Testing Basics](TESTING_BASICS.md). It covers the traps that are easy to fall into on real hardware, and what to do when the standard features are not enough.

## pytest fundamentals

Four mechanisms come up again and again in this guide, so here they are up front.

### How tests are collected

pytest runs automatically only what matches both of these.

- A `.py` file whose name starts with `test_`
- A function inside it whose name starts with `test_`

**Put differently, dropping the `test_` prefix means it is not called automatically.** That is worth remembering.

The most common use is helper functions. A helper written in a test file must not start with `test_`. If it does, pytest collects it as a test and treats its arguments as fixtures, which fails.

```python
# Do not start a helper with test_
def wait_ready(dut):
    ...


def test_actual(dut):
    wait_ready(dut)
```

**Test file names must be unique across the whole project.** Two files with the same basename fail at collection time.

```text
import file mismatch:
imported module 'test_plain' has this __file__ attribute:
  .../no_ino/test_plain.py
which is not the same as the test file we want to collect:
  .../with_ino/test_plain.py
```

In a directory with no `__init__.py`, a file's basename becomes its module name. Naming files after the sketch directory, as `test_<sketch name>.py`, keeps them unique without thinking about it.

**Keep names unique even for files you never intend to run together.** While you run them separately nothing shows, and the error appears the first time someone runs everything. `--import-mode=importlib` allows duplicates, but unique names are the simpler answer.

You can also use it to disable a test temporarily, but that is not recommended. Renaming hides the fact that it is disabled. Use a form that keeps the reason visible, which means a marker.

### What a marker is

A marker is a label attached to a test, written as `@pytest.mark.<name>` above the test function.

pytest knows the meaning of several of them.

| Marker | What it does |
| --- | --- |
| `skip` | Always skip. The reason goes in `reason` |
| `skipif` | Skip only when a condition is true |
| `xfail` | The failure is known. Failing does not turn the run red |
| `parametrize` | Run the same test several times with different values |

To disable a test, write this.

```python
@pytest.mark.skip(reason="waiting for hardware")
def test_pending(dut):
    ...
```

It then shows up in the results as skipped, with the `reason` printed, so both the fact and the reason survive. That is the difference from dropping the `test_` prefix.

**You can also invent your own markers.** pytest does not know what they mean, so they are for selecting with `-m`. Register one in the ini before using it, or you get a warning. Adding `--strict-markers` turns that warning into an error, which catches typos.

```ini
[pytest]
markers =
    slow: takes a long time to run
```

```bash
pytest -m "not slow"    # run everything except slow
pytest -m slow          # run only slow
```

This same form comes up again below, in keeping tests out of the default run.

### What conftest.py is

`conftest.py` is a file pytest loads by itself. Put it in the same directory as your tests, or in any directory above them. There is no import; being there is enough.

**It applies below where you put it.** At the project root it applies to everything; in a sketch directory it applies to that sketch and below. When both define a fixture of the same name, the one nearer the test wins.

There are two main things to write in it.

- **Fixture definitions.** Setup and cleanup shared by several test files.
- **Hook implementations.** Write a function with a set name such as `pytest_runtest_setup` and pytest calls it at the right moment. That lets you insert work at positions a fixture cannot express, like "before a test" or "at the end of the session".

It is powerful, but pick your moments. The reasoning and the real uses are covered later, under "conftest.py is a last resort".

### Config files: pytest.ini and pyproject.toml

pytest reads its settings from exactly one file. There are four candidates, and the higher one wins.

1. `[pytest]` in `pytest.ini`
2. `[tool.pytest.ini_options]` in `pyproject.toml`
3. `[pytest]` in `tox.ini`
4. `[tool:pytest]` in `setup.cfg`

A `pytest.ini` wins even when it is empty. **Have two and one of them is ignored entirely.** When a setting has no effect, first suspect that the other file is the one being read. The run prints which one as `configfile:`.

The syntax differs by format.

```ini
# tests/pytest.ini
[pytest]
testpaths = unit suites
addopts = -m "not manual"
markers =
    manual: needs a person
```

```toml
# tests/pyproject.toml
[tool.pytest.ini_options]
testpaths = ["unit", "suites"]
addopts = "-m 'not manual'"
markers = [
    "manual: needs a person",
]
```

TOML values are typed, so multi-line settings are arrays. For a value containing quotes, such as `addopts`, use different quotes outside and inside.

These are the settings you reach for most.

| Setting | What it does |
| --- | --- |
| `testpaths` | Which directories to run when given no arguments |
| `addopts` | Options added to every run |
| `markers` | Registering your own markers |
| `filterwarnings` | How warnings are treated |

This plugin's own repository sets `testpaths = ["tests"]` in `pyproject.toml`, so a bare `pytest` runs only the plugin's own tests. Running anything under `examples/` means naming it explicitly.

How to separate tests whose availability depends on the bench is covered in the next section.

## Permanent bench equipment versus occasional equipment

Bench equipment falls into two kinds.

- **Permanent equipment.** Always connected and usable in the default run.
- **Occasional resources.** Set up only for particular tests: an extra board, a sensor, an analyzer, a switch that can cut power, and **a person's hands as well.** A test that needs someone to press a button, unplug a cable or hold a magnet near the board can only run while that someone is there.

**The dividing line is not the board count, it is whether the default run can always assemble what it needs.** Equipment and people count the same way. With three permanent boards, three-board tests belong in the default run. With one permanent board, two-board tests are the occasional kind.

### The plugin takes care of peer boards

If a peer's port or profile cannot be resolved, **the tests using that peer are skipped**. They do not fail.

```text
SKIPPED [1] peer device2: port is not resolved
```

So an extra board usually needs no conftest at all. Where the board is attached and its port configured, the test runs; where it is not, the test is skipped quietly. CI and the workbench can share the same test files.

### Equipment the plugin knows nothing about is yours to check

For equipment the plugin has no idea exists, such as a sensor, an analyzer, or a switch that can cut power, check for it yourself and skip.

```python
# manual/conftest.py
import os

import pytest


def pytest_runtest_setup(item):
    if not os.environ.get("TEST_POWER_SWITCH"):
        pytest.skip("no power switch configured")
```

Put the conftest in a directory and it applies only below that directory.

### What cannot be detected automatically stays out of the default run

**A test that needs a person cannot be gated on an environment variable.** Neither the plugin nor the test can know whether someone is standing there. A test that takes a very long time is similar: the hardware is present, but you do not want it on every run. Keep these out of the default run and name them when you want them. There are three ways.

**Separate by directory.** Leave it out of `testpaths` and name it when you want it.

```bash
pytest                 # only what testpaths names; manual is not included
pytest manual/         # only when you want it
```

**Separate by marker.** Register it in the ini and exclude it by default.

```ini
[pytest]
markers =
    manual: needs equipment that is not always attached, or a person
addopts = -m "not manual"
```

```bash
pytest -m manual       # only the marked ones
```

**Drop the `test_` prefix from the file name.** This uses the collection rules in reverse. A file not named `test_*.py` is not collected automatically, but **naming the file directly skips the pattern check and collects it.**

A test file has to sit inside a sketch directory, so it goes in a per-sketch directory rather than loose under `manual/`.

```text
  manual/
    manual_power_cycle/
      manual_power_cycle.ino
      sketch.yaml
      manual_power_cycle.py   <- does not start with test_
```

```python
# manual/manual_power_cycle/manual_power_cycle.py
def test_power_cycle(dut):     # the function still needs test_
    ...
```

```bash
pytest                                                  # not collected
pytest manual/                                          # not collected
pytest manual/manual_power_cycle/manual_power_cycle.py  # only this collects it
```

**Note that naming the directory does not collect it.** You have to name the file. To run several, use shell expansion.

```bash
pytest manual/*/*.py
```

Nothing has to be registered in the ini and `testpaths` needs no adjusting, which makes this **the easy choice for tests you run one at a time.** Tests operated by a person usually are run one at a time, so it fits. The cost is that the name no longer says the file contains tests. If you often run them as a group, a directory or a marker suits better.

Any of the three is fine. The point is to **keep tests that always fail without the equipment or the person out of the default run.** Leave them in and failure becomes the normal state, which buries the real ones.

## Configuration precedence and `.env`

How ports and defines are substituted per environment. This lays out the whole picture behind the `.env` shown in [the basics](TESTING_BASICS.md).

### The primary DUT's port

Higher wins.

1. `--flash-port`
2. `--port`
3. `TEST_SERIAL_PORT_<PROFILE>`
4. `TEST_SERIAL_PORT`
5. `profiles.<profile>.port` in `sketch.yaml`, but only when it is a `socket://...` URL

`<PROFILE>` is the profile name upper-cased with `-` replaced by `_`.

### A peer DUT's port

A peer does not inherit the primary's setting. Each is resolved by name.

1. `--peer-port <name>:<port>`
2. `TEST_SERIAL_PORT_PEER_<NAME>_<PROFILE>`
3. `TEST_SERIAL_PORT_PEER_<NAME>`
4. A `socket://...` URL in `sketch.yaml`
5. If nothing resolves, the tests using that peer are skipped

`<NAME>` is the directory name without `peer_`, upper-cased. For `peer_echo` it is `ECHO`.

### Defines at compile time

In `build_config.toml`, the left side of `[defines]` is an environment variable name and the right side is the define name on the C/C++ side.

```toml
[defines]
TEST_WIFI_SSID = "WIFI_SSID"
TEST_WIFI_PASSWORD = "WIFI_PASSWORD"
```

```bash
# .env
TEST_WIFI_SSID=my-ssid
TEST_WIFI_PASSWORD=my-password
```

An unset variable passes an empty string rather than failing. If a value is required, put a check for the empty string in the sketch or the test.

### Choosing between them

- **`.env`**: the standing settings for that machine. Not committed.
- **Command-line options**: a temporary override. They beat `.env`, which is what you want when trying a different board.
- **A `socket://` in `sketch.yaml`**: a destination that does not depend on a board, as with a host core. This can be committed and shared.

In CI it is easier to skip `.env` and pass the values as environment variables from secrets. If you only run a host core, no port configuration is needed at all: the `socket://localhost` in `sketch.yaml` is used as it stands.

## Traps in expect

### Terminate a trailing variable-length field at the end of the line

A serial line arrives in fragments. If the last part of your pattern is variable-length and is not terminated by a newline, the match can settle before the rest of the line arrives, and you read a truncated value.

In one real case a device printed `data=abcdef12` and the test read `data=abcdef1`.

```python
# Bad: the final capture can settle early
dut.expect(re.compile(rb"data=([0-9a-f]+)"))

# Good: stop at the end of the line
dut.expect(re.compile(rb"data=([0-9a-f]+)\r?\n"))
```

If another literal from the same pattern follows the capture, there is no problem: the match cannot settle until that literal arrives.

### Output after the match is not guaranteed

`dut.expect(...)` stops reading as soon as the pattern matches. Bytes the device sends after that are not guaranteed to reach `dut.log`, which can end mid-line. When you need the tail, either print an end marker and `expect` it, or drain explicitly.

```python
import pexpect

dut.expect_exact("the last line I care about")
dut.expect(pexpect.TIMEOUT, timeout=2)   # read whatever still arrives
```

## Where logs and artifacts live

There are two kinds, and they behave differently.

**Serial logs are managed by `pytest-embedded`.** Every run creates a directory stamped with a UTC timestamp, holding one directory per test with its `dut.log`. **Because each run gets its own directory, an earlier run's logs are never overwritten.** `--root-logdir` changes where they go. This plugin also writes result files into the same place (`PASSED.txt` / `FAILED.txt` and friends, `SUMMARY.txt`, `summary.json`).

So **archiving logs after a run is usually unnecessary**. Consider it only when you want to collect them somewhere specific as CI artifacts, or to tidy up an accumulation.

**Files the sketch writes itself are a different matter.** When a sketch running on a host core writes with something like `fopen("output/...", ...)`, the working directory at run time is the sketch directory, so the file lands in `tests/<name>/output/`. That path is not per-run, so **files from the previous run remain**. A stale file can make a failing run look like it passed. Wiping it is the single most common reason for a conftest, as the next section shows.

## Cleaning up after an early exit

When a test stops partway through, any cleanup written at the end of it never runs. That is true for a failed `assert`, for an `expect` timeout, and for Ctrl-C. The board is left in an intermediate state.

If another test follows in the same module, it inherits that state. If none does, the state persists after the run finishes. Leave BLE advertising on and it keeps showing up in the scans of the bench next to you.

A pytest fixture's finalizer runs even when the test fails, and even on Ctrl-C. Use that.

```python
# tests/device/conftest.py  ... every test under this directory uses dut
import pytest


@pytest.fixture(autouse=True)
def leave_quiet(dut):
    yield
    dut.write("stop\n")
    try:
        dut.expect_exact("STOPPED", timeout=2)
    except Exception:
        pass
```

There are two limitations.

- **An autouse fixture that requests `dut` demands a board for every test under that directory.** You cannot put it where tests that need no hardware also live. Put it in the conftest of a directory that holds only device tests.
- **It does not reach peers.** If an autouse fixture requests `peers`, it trips the peer activation check, so every test counts as a peer test and peers get built and uploaded every time.

What to stop is up to the project. These judgements have held up in practice.

- **Always stop BLE advertising and scanning.** Otherwise you interfere with the benches around you.
- **Stop PWM, servos and driven GPIO.** Anything that keeps moving physically is a hazard.
- **Peripherals such as USB are often harmless to leave up.** Arduino's USB stack cannot stop presenting the device once begun. When something cannot be stopped, clean up as far as you can and leave it there.
- **Reply when the state has been reached, not when the command was received.** Restarting advertising or closing every link takes time. Replying on receipt lets the run move on while the work is unfinished.

**Cleanup is not a substitute for normalizing state at the start of a test.** Cleanup protects the environment. A test's own correctness, and being able to run it alone with `-k`, are the job of its own start-up. Never write a test that assumes the previous test's cleanup succeeded.

## conftest.py is a last resort

`conftest.py` is pytest's extension point. Put it in the same directory as your tests, or any directory above them. Placed high up it applies to the whole project; placed in a sketch directory it applies to that sketch only.

**First check whether the standard features are enough.** This is what the plugin already provides, and it covers most needs.

- Profile selection (`--profile`, `default_profile` in `sketch.yaml`)
- Port resolution (`--port`, `TEST_SERIAL_PORT_<PROFILE>`, a `socket://` port in `sketch.yaml`)
- Controlling how far a run goes (`--run-mode=all|build|test`)
- Injecting compile-time defines (`build_config.toml`)
- Peer DUTs (`peer_<name>/` and `peers`)
- Exclusive access to a physical device (`--device-lock`)
- A result summary written into the log directory
- Device-side assertions (Unity, ArduTest)

There are still cases that need a conftest. The following are forms actually used in real projects.

### 1. Delete files the sketch wrote, before the run

The most common use. A file left from the previous run can make a failing run look like it passed.

```python
import shutil
from pathlib import Path


def pytest_runtest_setup(item):
    output_dir = Path(item.fspath).parent / "output"
    if output_dir.exists():
        shutil.rmtree(output_dir)
```

**There is a reason this is a hook and not a fixture.** `pytest_runtest_setup` runs before the `dut` fixture builds and launches the sketch. Written as a fixture, the deletion could race the sketch's writes. The hook makes the order certain.

Be aware that this form deletes any directory named `output`, unconditionally. Check what is in there before copying it into another repository.

### 2. Rewrite configuration before the compile

For instance, swapping the platform version in `sketch.yaml` for the duration of a run.

```python
def pytest_collection_finish(session):
    # rewrite before the plugin compiles anything
    ...


def pytest_sessionfinish(session, exitstatus):
    # put it back
    ...
```

**`pytest_collection_finish` is used** because it is guaranteed to happen before any compile, whatever fixture order pytest picks. A crash between the rewrite and the restore leaves the working tree modified, so a real implementation also saves the original somewhere outside the repository.

### 3. Share a query helper across sketches

Method A from [the basics](TESTING_BASICS.md) as a fixture. It goes in a conftest because several suites use it.

```python
import pexpect
import pytest


@pytest.fixture
def probe():
    def ask(target, command, pattern, attempts=12, timeout=5):
        for _ in range(attempts):
            target.write(command)
            try:
                return target.expect(pattern, timeout=timeout)
            except pexpect.TIMEOUT:
                continue
        raise AssertionError(f"no answer to {command!r} matching {pattern!r}")

    return ask
```

### 4. Audit serial logs and add to the report

For catching the case where a test passed but the log contained something worrying. A fixture reads the log, `pytest_runtest_makereport` adds a section to the report, and `pytest_terminal_summary` sums up the run. **The report hooks are only available in a conftest.**

**Do not let that fixture request `dut`.** If it does, it is set up after `dut` and finalized before it, so it can never read the tail of the log. Requesting only `test_case_tempdir` gives the correct order.

### 5. Prepare the environment before a run

For work such as symlinking a local platform into the Arduino directory. It has to happen once, before any build, so it belongs in a session-scoped autouse fixture.

### 6. Helpers for unit tests that use no hardware

`tests/` can also hold plain Python tests that need no board. Put them in a directory with no `.ino` and this plugin compiles nothing, uploads nothing, and they run as plain pytest. Their fixtures are ordinary pytest usage and have nothing to do with the plugin.

### When you do not need a conftest

- **A helper used only inside one test file.** Write it as a plain function in that file.
- **Switching ports or profiles.** Options and environment variables cover it.
- **Per-test initialization.** Writing it at the top of the test body keeps it visible to the reader.

## Observing the board's state

It is tempting to check the board's state after a run, but **connecting to the same board and asking gives an answer you cannot trust.**

Opening the serial port makes pyserial assert DTR and RTS. That is the default behaviour of opening a port, not something the plugin does to force a reset. On a board that wires those two lines straight to EN, it is a reset. What answers your query is then a freshly booted sketch. Check that advertising really stopped and you get the boot state back, which looks like a failure. Dropping both lines before opening does not help. In one real case the peer answered `ADVERTISING 1` and a Classic DUT simply replayed its startup output.

**Whether it resets depends on the board.** Boards with an auto-reset circuit in between usually do not reset on a plain open. Nor do native USB CDC boards, though they reboot when the port is opened at 1200 bps. **Either way, connecting to the target board to check is not trustworthy.** On a resetting board you read the boot state, and even on a board that does not reset, the connection itself can affect what the sketch does.

**Observe from a different board.** Leave the target alone and flash an observer sketch onto a second board to listen. And **take a control measurement**. "I heard nothing" is also what you get from a broken observer. Reset the target back to its boot state and confirm the same observer can hear it.

### Why there is no option to leave DTR and RTS alone

The plugin has no option to change this behaviour, and that is deliberate.

To begin with, **"leave them alone" is not one of the choices.** Once the port is open, those two lines carry some level. Not asserting them only means they fall to the deasserted side, or keep whatever state the driver had. On the classic ESP32 circuit DTR drives IO0 and RTS drives EN, so holding them deasserted can put the chip into download mode on the next reset. The option would therefore not be "do not touch" but "which level to open with", and the right value differs per board.

Next, **a reset on connect is harmless when tests are stateless.** Each test establishes the state it needs, so a reset costs nothing. It only hurts tests that accumulate state within a module, and that is a form to avoid anyway.

There is one condition that could justify it: **a board that resets on connect together with a start-up that takes seconds.** With several tests in a module you pay the boot time on every one of them. With one test per module the upload time dominates and the difference barely shows.

A project that truly needs it has a way out. `pytest-embedded`'s `Serial` accepts an already-constructed pyserial object in place of a port string. A conftest can override the `serial` fixture, prepare the object with `do_not_open=True`, set DTR and RTS, and then open it. The right choice is board-specific, which makes it conftest material rather than a plugin option.

## Principles for peer tests

Policies that have held up for tests with two or more boards.

- **Narrow the partner down with a test-only identifier.** For BLE, use a test-only 128-bit service UUID to exclude the devices around you. Do not decide who to connect to from the device name alone.
- **Make pass or fail decidable from the serial logs of both sides.** Guessing from one side leaves you unable to tell which side is at fault.
- **Stop scanning, advertising, subscriptions and connections at the end of every test.**
- **Allow a timeout for transient radio delays, but do not retry without limit.** Unlimited retries hide defects.
- **Cross-check the disconnect reason, the MTU and the security state on both sides** wherever you can.
- **Where possible, make one side a direct implementation over the standard library.** Two copies of your own library cannot demonstrate interoperability.
- **For tests that carry state, state the state at start and at end explicitly.** This matters most for things that survive a run, such as bonds and NVS.

## Do not affect the outside world at boot

With peers, the flashing order needs care. The primary upload runs first, at module level, and the peer upload runs during the first test's setup. In other words, **the peer is flashed after the primary has booted and run `setup()`**.

If the primary brings up radio or USB in `setup()`, it can observe the resets and enumerations caused by flashing the peer, and record them as errors. That is not a defect in the sketch.

The fix is to **start nothing that affects the outside world in `setup()`, and start it when the test says so**. Enable it on the first line of the test body, by which point the peer has already been flashed.
