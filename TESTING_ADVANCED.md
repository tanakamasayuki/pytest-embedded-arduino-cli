# Advanced Testing

[日本語](TESTING_ADVANCED.ja.md)

A follow-on from [Testing Basics](TESTING_BASICS.md). It covers the traps that are easy to fall into on real hardware, and what to do when the standard features are not enough. When something has already gone wrong, [the FAQ](TESTING_FAQ.md) indexes this guide by symptom.

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

There are two kinds of thing to write in it, and they differ in **who chooses the name.**

| Kind | Name | How it gets called |
| --- | --- | --- |
| hook | pytest decides it; you cannot invent new ones | pytest calls it at the moment that name stands for |
| fixture | You decide it | Called when a test or another fixture takes it as an argument, or unasked with `autouse=True` |

**A hook means implementing one of a fixed set of names.** `pytest_runtest_setup` runs just before each test, `pytest_sessionfinish` at the end of the session. That lets you insert work at positions a fixture cannot express, like "before a test" or "at the end of the session". The full list of names is in the Hooks section of the official reference.

<https://docs.pytest.org/en/stable/reference/reference.html#hooks>

A typo will not pass silently. Names beginning with `pytest_` are validated as hooks, so writing `pytest_runtest_setupp` aborts the run with an `unknown hook` error. A name that does not begin with `pytest_` is simply an ordinary function and is ignored.

**The hook names are pytest's alone.** Plugins do not add hook names; neither `pytest-embedded` nor this plugin does. What a plugin does is implement pytest's hooks and add fixtures and options. So when you are looking for a hook to write in a conftest, pytest's reference is the only place to look.

| Layer | What it adds |
| --- | --- |
| pytest | The hook names, the built-in fixtures, the standard options |
| `pytest-embedded` | Fixtures such as `dut`; options such as `--port`, `--baud`, `--root-logdir` |
| This plugin | Fixtures such as `peers`, `arduino_test`, `arduino_cli_app`; options such as `--profile`, `--run-mode`, `--device-lock` |
| Your project | Fixtures, and implementations of pytest's hooks |

**Fixture names are yours, so you can add as many as you like.** List the ones currently available with the command below. It also shows what this plugin and `pytest-embedded` provide, such as `dut`, `peers` and `arduino_test`.

```bash
pytest --fixtures
```

How to write them is in the Fixtures section of the official reference.

<https://docs.pytest.org/en/stable/reference/fixtures.html>

**Fixtures can also live in a test file; hooks cannot.** A hook written in a test file is never called. So `conftest.py` is only strictly needed when you need a hook; when a fixture is enough, the test file is the safer place because its reach is narrower.

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
testpaths = unit single loopback peer
addopts = -m "not manual"
markers =
    manual: needs a person
```

```toml
# tests/pyproject.toml
[tool.pytest.ini_options]
testpaths = ["unit", "single", "loopback", "peer"]
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
| `norecursedirs` | Which directories collection does not descend into |
| `addopts` | Options added to every run |
| `markers` | Registering your own markers |
| `filterwarnings` | How warnings are treated |

This plugin's own repository sets `testpaths = ["tests"]` in `pyproject.toml`, so a bare `pytest` runs only the plugin's own tests. Running anything under `examples/` means naming it explicitly.

**`testpaths` is a convenience, not a guard, and it is worth being clear which one you wanted.** It decides what a bare `pytest` collects. **Name a path and it is ignored**, so `pytest manual` runs everything named `test_*.py` under `manual/` regardless of what `testpaths` says. If you were relying on it to keep something from running by accident, it was never doing that job.

It has a second weakness, in the direction people usually argue about. **Add a suite directory, forget to list it, and its tests silently drop out of the default run.** Nothing warns; the run reports all green while a whole directory goes unexecuted, which is the same shape as a check that quietly stops checking.

**`norecursedirs` is the better tool for the same job.** It names directories collection does not descend into, so the default becomes everything minus what you excluded. **A directory added later is picked up on its own**, which removes the silent case entirely — that is the whole difference, and it is why one project switched to it with the reasoning written into the config comment.

**Neither of them is a guard, though.** Measured against naming the directory directly, both let it run.

| Mechanism | Bare `pytest` | The directory named | A directory added later |
| --- | --- | --- | --- |
| `testpaths` | excluded | **runs** | **silently dropped** |
| `norecursedirs` | excluded | **runs** | picked up |
| a marker plus `addopts = -m "not manual"` | excluded | deselected | picked up |
| dropping the `test_` prefix | excluded | nothing collected | picked up |

The marker survives a named path because `addopts` is added to every run, not just the bare one. **Dropping the prefix is stronger still, because it depends on no configuration at all** — the file is invisible to collection until you name the file itself, so no config mistake can expose it. That is the form *What cannot be detected automatically stays out of the default run* recommends, and this is why.

**So: exclude with `norecursedirs` rather than listing with `testpaths`, and guard with the prefix.** If you list with `testpaths` anyway, close the silent-omission case with one test that compares the directories against the setting. It needs no hardware.

```python
TESTS_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {"manual"}          # deliberately out of the default run
NOT_SUITES = {"sketch_support", "__pycache__"}


def test_testpaths_cover_every_suite(pytestconfig):
    listed = set(pytestconfig.getini("testpaths"))
    found = {
        p.name for p in TESTS_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in NOT_SUITES
    }
    unaccounted = found - listed - EXCLUDED
    assert not unaccounted, f"in neither the default set nor the excluded set: {sorted(unaccounted)}"
```

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

**This skipping is for peers only.** The primary DUT is never skipped; it fails instead, in one of three shapes.

**The upload runs before the connection.** So when nothing is behind the port you named, it fails at the upload, not at the connection. That changes where in the log to look, so here they are in order.

| The primary's situation | Where it fails |
| --- | --- |
| No port configured at all | Preparing the connection, with `ValueError` |
| Nothing behind the port you named, including a dangling symlink | **The upload.** `arduino-cli` fails and you get `CalledProcessError` |
| The device disappears between upload and connection | The connection, with `FileNotFoundError` |

Writing a symlink such as `/dev/serial/by-id/...` into `.env` makes the middle case easy to hit: **the string resolves while the device is absent.** On a bench where a supposedly permanent board has been unplugged, the default run fails right there. The primary is the thing under test, so its absence is treated as a configuration error, never a skip.

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

If none of them resolves, the run **fails rather than skipping**. That is the difference from a peer.

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

A serial line arrives in fragments. If the last part of your pattern is variable-length and is not terminated by a newline, the match can settle before the rest of the line arrives, and you read a truncated value. **This is a race**: nothing decides whether your read arrives before or after the rest of the line, so the same test can pass on one run and fail on the next, and it can also pass while handing you the wrong value. *A test that passes and fails at random* covers the whole class.

In one real case a device printed `data=abcdef12` and the test read `data=abcdef1`.

```python
# Bad: the final capture can settle early
dut.expect(re.compile(rb"data=([0-9a-f]+)"))

# Good: stop at the end of the line
dut.expect(re.compile(rb"data=([0-9a-f]+)\r?\n"))
```

If another literal from the same pattern follows the capture, there is no problem: the match cannot settle until that literal arrives.

**Writing `[^\r\n]*` to "stop at the end of the line" is not enough either.** It matches zero characters too, so the match settles before the line has finished arriving. To guarantee a complete line, include `\r?\n` in the pattern. In one suite an audit found patterns of this shape across several files, and **the one that actually broke a test was not the one that used a value which could be truncated.**

### Output after the match is not guaranteed

`dut.expect(...)` stops reading as soon as the pattern matches. Bytes the device sends after that are not guaranteed to reach `dut.log`, which can end mid-line. When you need the tail, either print an end marker and `expect` it, or drain explicitly.

```python
import pexpect

dut.expect_exact("the last line I care about")
dut.expect(pexpect.TIMEOUT, timeout=2)   # read whatever still arrives
```

### Do not blame a structural change for a failure it merely exposed

When a test fails right after you change how a fixture is placed or ordered, it is tempting to conclude the change broke it. But there is a case where **all the change did was alter when lines arrive, and what was broken was the reading side, which had always been wrong.** The device log showed the state was correct; only the string the test received was cut short.

**When you see a failure, check the device log first to confirm the code under test is actually wrong.** Timing-dependent bugs surface the moment you change the structure. The change exposed it; the change did not create it.

## Where logs and artifacts live

There are two kinds, and they behave differently.

**Serial logs are managed by `pytest-embedded`.** Every run creates a directory stamped with a UTC timestamp, holding one directory per test with its `dut.log`. **Because each run gets its own directory, an earlier run's logs are never overwritten.** `--root-logdir` changes where they go. This plugin also writes result files into the same place (`PASSED.txt` / `FAILED.txt` and friends, `SUMMARY.txt`, `summary.json`).

So **archiving logs after a run is usually unnecessary**. Consider it only when you want to collect them somewhere specific as CI artifacts, or to tidy up an accumulation.

**Files the sketch writes itself are a different matter.** When a sketch running on a host core writes with something like `fopen("output/...", ...)`, the working directory at run time is the sketch directory, so the file lands in `tests/<name>/output/`. That path is not per-run, so **files from the previous run remain**. A stale file can make a failing run look like it passed. Wiping it is the single most common reason for a conftest, as the next section shows.

## Cleaning up after an early exit

Cleanup written at the end of a test body **does not run when the test stops partway through.** That is true for a failed `assert`, an `expect` timeout, and Ctrl-C.

```python
# Bad: an expect failure never reaches the stop
def test_advertise(dut):
    dut.write("start\n")
    dut.expect_exact("ADVERTISING 1")
    dut.write("stop\n")            # not executed if the line above fails
```

The board is left in an intermediate state. If another test follows in the same module, it inherits that state. If none does, the state persists after the run finishes. Leave BLE advertising on and it keeps showing up in the scans of the bench next to you.

**Move the cleanup into a fixture's teardown.** A fixture's teardown runs even when the test fails and even on Ctrl-C, so the cleanup happens however the test ended.

### Start by writing it in the test file

What to clean is specific to that sketch, so the test file is the natural place. `conftest.py` is a last resort.

```python
import pytest


@pytest.fixture(autouse=True)
def cleanup_device(dut):
    yield
    dut.write("stop\n")


def test_advertise(dut):
    dut.write("start\n")
    dut.expect_exact("ADVERTISING 1")
```

`autouse=True` applies it to every test in that file, and only to that module.

**The name is yours to choose**, with two rules.

- **Make it read as cleanup.** Something like `cleanup_device`, `stop_radio` or `release_pins`, so the name says what it does. An `autouse=True` fixture never appears by name in a test body, so the name is the only clue there is.
- **Do not start the name with `test_`.** It still works as a fixture, but **pytest silently leaves it out of collection, with no warning.** Anyone scanning the file reads it as a test, and the moment the `@pytest.fixture` decorator is lost, the function quietly becomes a real test.

**The port being open during the cleanup is guaranteed.** Because the fixture requests `dut`, it is set up after `dut` and torn down before it.

To clean peers as well, take `peers` as an argument.

```python
@pytest.fixture(autouse=True)
def cleanup_device(dut, peers):
    yield
    for device in [dut, *[peers[name] for name in sorted(peers)]]:
        device.write("stop\n")
```

**Waiting for a reply is optional.** The examples above only send. You can wait instead.

```python
@pytest.fixture(autouse=True)
def cleanup_device(dut):
    yield
    dut.write("stop\n")
    try:
        dut.expect_exact("STOPPED", timeout=2)
    except Exception:
        pass          # a failed cleanup must not change the test result
```

Waiting has two benefits. It prevents the overlap where the port closes before things have stopped, the module teardown releases the lock, and another process starts an upload. It also leaves the outcome of the cleanup in the log.

Not waiting has two benefits of its own. It is simpler, and it works with a sketch that answers nothing. It also costs no time when the sketch is hung.

**If you do wait, swallow the exception.** A failed cleanup must not change the test result. A missing reply is not unusual: the sketch may not read commands at all, or it may be hung. A failed test that also carries a teardown error makes the real cause harder to see.

Note that without waiting, nothing guarantees the sketch finished reading the command before the port closed. Wait if you need that certainty.

### Move it to a conftest to share across modules

When writing the same cleanup into many modules gets tedious, move it into a `conftest.py`. It then applies below wherever you put it, and the body can stay exactly as it was in the test file.

**Mind where you put it.** An autouse fixture that requests `dut` demands a board for every test below it. It cannot go above a directory holding tests that need no board, such as `unit/`. Put it in a directory that holds only device tests.

```text
  tests/
    unit/                  <- keep it out of here
    single/
      conftest.py          <- put it here
      my_app/
        test_my_app.py
```

Taking `peers` as an argument is fine too. For a module with no `peer_*` directory it is simply an empty mapping, and nothing extra happens.

### The same name or a different one

`conftest.py` files in directories above are read as well. When a cleanup fixture exists both above and below, **the behaviour depends on whether the names match.**

| Name | Behaviour |
| --- | --- |
| The same | Only the nearer one runs. The one above is hidden completely |
| Different | Both run. The nearer one is torn down first, then the one above, then `dut` closes |

Use it like this. Give it the same name to **replace** the shared cleanup with something else for that sketch. Give it a different name to keep the shared one running and **add** something for that sketch only.

There is nothing to gain from splitting cleanup across several fixtures, so keep one fixture with the same name as the default.

### What to stop

**First ask what needs restoring, because the module structure decides that.** Stopping something and putting the board back the way it booted are different jobs, and the second one is where the bugs live.

- **One test per module: stopping is enough.** Nothing carries over inside the module, and the next module begins with an upload, which resets the board. **There is no next test to restore state for**, so a command that rebuilds the boot state has no purpose. What remains is leaving the rig quiet for whoever uses it next, and stopping does that — sooner than the next upload would, which matters on a shared bench.
- **Several tests per module: restoring becomes necessary**, and it is error-prone. One project implemented both a stop and a restore-to-boot command, and every bug it hit was in the restore half: a counter reset without the listeners it counted, a callback not put back, a flag restored without the radio it described, a characteristic value left behind. **Restoring means enumerating everything you changed, and the failure mode is forgetting one.** A stop restores nothing, so that whole family of bugs cannot occur.

**When you do restore, restore the thing and not your copy of it.** Those bugs share a shape: **the state was not in the sketch's variables.** It was in a library's registry, a callback slot, a server attribute, the hardware. A variable that only mirrors one of those can be reset on its own, which puts the copy out of step with the reality — **worse than not restoring at all**, because the sketch now reports a state it is not in. Re-run the registration instead of re-assigning the mirror, and derive counts from the real thing rather than keeping your own. **And some actions cannot be undone:** disabling a radio controller until the next reset is a fact, not a setting. Restoring the flag that recorded it just resumes calling into something that is gone. The honest restore leaves that record standing and lets the next upload put the board back.

So the rule of one test per module buys something beyond execution time: **the restore code you never have to write.**

What to stop is up to the project. These judgements have held up in practice.

- **Always stop BLE advertising and scanning.** Otherwise you interfere with the benches around you.
- **Stop PWM, servos and driven GPIO.** Anything that keeps moving physically is a hazard.
- **Peripherals such as USB are often harmless to leave up.** Arduino's USB stack cannot stop presenting the device once begun. When something cannot be stopped, clean up as far as you can and leave it there.
- **If you take a reply, have the sketch send it once it has stopped.** Closing every link and stopping advertising take time. Reply on receipt and the test moves on while things are still running. A setup that takes no reply at all is fine too.

**Cleanup is not a substitute for normalizing state at the start of a test.** Cleanup protects the environment. A test's own correctness, and being able to run it alone with `-k`, are the job of its own start-up. Never write a test that assumes the previous test's cleanup succeeded.

### A reset does not necessarily clean anything

It is tempting to think that resetting the board instead of cleaning up puts it back. **That depends on the board.** Some come back exactly as they do from power-on; on others, parts keep running. **Do not assume it without checking.**

**How far a software reset initializes things is up to the board and its core.** If PWM output or driven GPIO survives, a reset is not a cleanup. And where a pin-hold feature is enabled, a reset may not release it.

Take ESP32 as an example. Arduino's `ESP.restart()` calls ESP-IDF's `esp_restart()`, whose contract reads:

> Peripherals (except for Wi-Fi, BT, UART0, SPI1, and legacy timers) are not reset.

So on that family, PWM and GPIO keep driving. With pin hold enabled, it stays held until power is removed or the release API is called. **Other boards behave differently.** Find out what comes back on the board you use, from the core's documentation or by measuring.

**A reset also runs the start-up code, which dirties things again.** This holds on any board. `setup()` executes a second time, so the advertising or the output you just stopped is recreated. The cleanup undoes itself. Avoiding that requires the sketch to start nothing at boot, as described under "Do not affect the outside world at boot".

**On a board that can tell you why it started, you can branch on it.** Distinguish a cleanup restart from a normal boot and start nothing in the former case. On ESP32 that is `esp_reset_reason()`.

```cpp
// on ESP32
void setup()
{
  Serial.begin(115200);

  if (esp_reset_reason() == ESP_RST_SW)
  {
    // restarted for cleanup: start nothing that reaches outside
    return;
  }

  startEverything();
}
```

Make sure `loop()` does not start it either. That API distinguishes power-on, software reset, panic, watchdogs and more, and which reasons should lead to staying idle is yours to decide. **On a board with no equivalent, this branch cannot be written.** There, do not lean on a reset; call the API that stops the thing.

**Be careful doing this to a peer.** A peer sitting idle answers no queries either, so **the symptom is indistinguishable from a dead board.** Keep at least a state query alive while idle, so the two can be told apart.

**A reset restores only as far as the reset signal reaches.** A servo keeps its angle, a relay keeps its contact, a latching display keeps what it shows. **A sticky status or error bit keeps its value too**, because it sits in a peripheral rather than in your variables. Devices on I2C or SPI keep their own configuration. The other end of a radio link never learns you reset.

**Some of what the reset does not reach sits on the same board.** A radio controller running on a companion chip, a communications module attached over UART, an external host controller. People think of one board as one device, so they expect a reset to stop the radio too. **It does not.** The main side restarts while the other chip holds its link or keeps advertising.

**Non-volatile storage survives by design.** Settings or logs a test wrote are still there after a reset. Clear them explicitly, or use a full-erase-on-upload facility if the platform has one. **The latter is spelled differently on each platform, and some platforms do not offer it at all.** On ESP32, for example, it is a modifier on the profile's `fqbn`. **The one that works everywhere is the former: clearing from the sketch.**

**On some boards a reset drops the port and re-enumerates it**, which is the case for native USB boards. A reset meant as cleanup can change what the next run connects to.

**How to initialize state differs per board and per feature.** There is no single procedure. For each thing you want stopped, find and call the API that stops it. **A reset is the last resort.** Calling the stop API is faster, more certain, and easier to reason about.

### A backstop for when the cleanup command never arrives

A sketch that has hung or crashed never reads the cleanup command. **And those are exactly the runs that leave the worst residue.** On a bench shared with other projects, the board is handed over still transmitting or still presenting USB.

Only one mechanism survives a dead sketch: **flashing something inert at the end of the session.** Flashing does not depend on the serial conversation, so it works even when the sketch does not.

Implement it in `pytest_sessionfinish` in a `conftest.py`. Every fixture is gone by then, so a hook is the only option.

**Take the device lock yourself.** The plugin's lock is module-scoped and released at module teardown, so it is no longer held at the end of the session. Flashing without it collides with whatever process was waiting. The lock is importable:

```python
from pytest_embedded_arduino_cli.device_lock import DeviceLock, DeviceLockInfo, default_lock_dir
```

The lock directory is the value of `--device-lock-dir`, or `default_lock_dir()` when that is unset. The key is the symlink-resolved port path. Track the boards yourself: relying on which ones the last test connected to misses every board that run did not touch.

This is slow. When the cleanup command is enough, use that instead.

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

This is not a constraint the audit introduces; it is one that **already holds.** The audit reads log files, which requires the serial listener to have flushed them, and that is only true because `dut` finalizes first. In other words, the reason to respect it is to avoid breaking something you already have.

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

Opening the serial port makes pyserial assert DTR and RTS. That is the default behaviour of opening a port, not something the plugin does to force a reset. On a board that wires those two lines straight to the reset pin, it is a reset. What answers your query is then a freshly booted sketch. Check that advertising really stopped and you get the boot state back, which looks like a failure. Dropping both lines before opening does not help. In one real case the peer answered `ADVERTISING 1` and a Classic DUT simply replayed its startup output.

**Whether it resets depends on the board.** Boards with an auto-reset circuit in between usually do not reset on a plain open. Nor do native USB CDC boards, though they reboot when the port is opened at 1200 bps. **Either way, connecting to the target board to check is not trustworthy.** On a resetting board you read the boot state, and even on a board that does not reset, the connection itself can affect what the sketch does.

**Observe from a different board.** Leave the target alone and flash an observer sketch onto a second board to listen. And **take a control measurement**. "I heard nothing" is also what you get from a broken observer. Reset the target back to its boot state and confirm the same observer can hear it.

### Why there is no option to leave DTR and RTS alone

The plugin has no option to change this behaviour, and that is deliberate.

To begin with, **"leave them alone" is not one of the choices.** Once the port is open, those two lines carry some level. Not asserting them only means they fall to the deasserted side, or keep whatever state the driver had. On the classic ESP32 circuit DTR drives IO0 and RTS drives EN, so holding them deasserted can put the chip into download mode on the next reset. The option would therefore not be "do not touch" but "which level to open with", and the right value differs per board.

Next, **a reset on connect is harmless when tests are stateless.** Each test establishes the state it needs, so a reset costs nothing. It only hurts tests that accumulate state within a module, and that is a form to avoid anyway.

There is one condition that could justify it: **a board that resets on connect together with a start-up that takes seconds.** With several tests in a module you pay the boot time on every one of them. With one test per module the upload time dominates and the difference barely shows.

A project that truly needs it has a way out. `pytest-embedded`'s `Serial` accepts an already-constructed pyserial object in place of a port string. A conftest can override the `serial` fixture, prepare the object with `do_not_open=True`, set DTR and RTS, and then open it. The right choice is board-specific, which makes it conftest material rather than a plugin option.

## Building a clean test plan

Adding a second test to a module is cheap in itself. The upload happens once per module, so a test after the first adds only a reconnect. **That much is board-dependent, though: where opening the connection resets the board, it re-runs the boot as well.** Two things make it expensive: **per-test setup and cleanup**, and **order dependence**. The first costs time, the second costs complexity.

A test plan breaks down when tests start depending on each other, not when they multiply. And **the moment you have to care about order, that test is designed wrong.** The reverse-order check below is not a tool for managing order. **It is a tool for finding design errors.** When it finds one, fix the design rather than pinning the order.

### The layers of a plan

A plan is not one run. It is several layers, cheap and frequent at the bottom, expensive and rare at the top. Each layer answers a question the layer under it cannot.

1. **Unit tests on a host core.** No hardware, so they run anywhere including CI, and several can run at once. Logic, parsing, state machines. Run these the most often — they are the cheapest thing you own, and nothing above them tells you a boundary condition is wrong as quickly.
2. **Module tests for what you just touched.** Real hardware, but only the modules related to the change in front of you. This is the loop you sit in while working.
3. **A clean full run, with `--clean`.** Everything, from scratch, in one invocation. This is where order dependence and leftover state surface, which is exactly what running a subset hides. Before a merge or a release.
4. **Build tests.** Compile the examples for every profile you claim to support. No device, no serial, no judgement about behaviour — only "does it still build".
5. **Manual tests, where they apply.** Things a person has to look at, listen to, or unplug. They stay out of the default run, and where they belong in the order depends on what they check.

**Plain pytest coexists with all of this.** A test that takes neither `dut` nor `peers` is an ordinary pytest test, and it runs in the same invocation as everything else. Checking a data table, a generated header, the bytes of a descriptor — none of that involves a core, so write it as normal Python and simply do not depend on the device fixtures.

**There is one condition, and it is not the fixtures.** What triggers a compile and an upload is **an `.ino` sitting in the same directory**, not whether a test asked for `dut`. Put a hardware-free test next to a sketch and the build runs before it anyway, for nothing. **Keep those tests in a directory with no `.ino`** and the plugin does nothing at all for them.

**Below the host core there is one more option.** Code that touches no Arduino API at all — a codec, a parser, a lookup table — can be compiled straight with the system compiler and run as an ordinary program. The test calls the compiler, then runs the binary and checks its exit status. It needs neither a board nor a core install, and it is the fastest thing available.

**What you give up is the wrapping.** A host core hides the OS-dependent parts for you; a bare compiler call does not. The compiler's name, the flags, the path the binary lands at, even the signedness of `char` — which differs between your machine and the target — are all yours to get right, and nothing checks them for you. **The result may not run on another OS, or on a CI runner that is not yours.** Take this route when the code under test really is OS-independent, and go in knowing the harness around it is not.

**About `--clean` on the full run.** It passes through to the compile, so nothing from a previous build is reused, and this plugin also clears the ArduTest artifacts before the run. **Most of the time you can leave it off** — an incremental build is much faster and nothing goes wrong. **Put it on when you have bumped a library or the core version.** Reuse is what makes the ordinary build fast, and a version bump is exactly when you no longer want it. **Before a release, run the full test with `--clean`.**

**The build layer is the one this plugin does not cover.** Everything else here runs through it, manual tests included — those are the same machinery, merely excluded from the default selection. A build test has no device, no serial port and no fixture to ask for: it is `arduino-cli compile` over a matrix. Wire it up separately rather than waiting for the plugin to grow into it.

**Nothing below the build layer asks its question**, because each of those runs builds one sketch for one profile. A change can pass every device test you own and still break a profile you never flash.

### Build tests grow with the product, not the sum

Examples times profiles. One more example adds a row, one more profile adds a column, and a compile is not fast. Run the whole grid on every push and you will stop pushing. Split it in two.

- **A narrow check on every push.** The profiles that matter most, all examples. Enough to catch a change that breaks the build.
- **The full sweep on demand.** Every profile, or every core version. Before a release, by hand, not on every push.

**Parallelism is what makes the sweep bearable**, and hosted CI hands it to you: one job per profile or per core version, running at the same time, so the wall clock becomes the slowest job instead of the sum. GitHub Actions' matrix is the usual way. What matters in practice:

- **One failure must not cancel the other jobs.** A build matrix is a coverage report and you want every cell, so turn off fail-fast.
- **Cache the installed platform**, keyed on whatever pins its version, so a job that is not bumping the core does not download it again.
- **A coverage matrix should record pass, fail or not-applicable per cell and still exit successfully.** A red cell is information. A gate that has to block a merge is a separate job with a separate rule.
- **Watch the disk.** A platform install can be large, and several in one job may not fit. Decomposing into one core version per job is the way out.
- **Skip cleanly.** An example that does not declare a given profile should be reported as not applicable, not as a failure.

Real workflows in the shapes above are linked from [Example Projects](TESTING_EXAMPLES.md).

### Three shapes that do not work

These three turned up in practice. All of them depend on what an earlier test did, and all of them are design errors. Remove the dependency rather than working around it by fixing the order.

**1. Free-riding on state an earlier test created.** Asserting on an accumulating value, such as a counter or a connection count, that an earlier test produced.

- Symptom: it fails when run on its own.
- Fix: establish the state yourself at the start.

**2. Depending on being first.** Waiting for a line the sketch prints once at boot. Let another test run first and that line has already gone by.

- Symptom: it passes alone but fails with the whole module, and fails when reordered.
- Fix: stop waiting for the announcement and query the state instead.

**3. Asserting a pristine state that another test dirties.** One test assumes nothing is connected while another deliberately leaves a connection up.

- Symptom: the result changes with the execution order.
- Fix: rebuild the state you assume at the start of the test. If there seems to be no way to rebuild it, read the next section but one.

### Split the module for a destructive test

Some tests leave the board unusable: they disable a peripheral, or write a setting that only a reset undoes. Such a test looks as though it has to run last.

**That is not a reason to order several tests; it is a reason to split the module.** Put it in its own module and the next upload restores the board, so **the ordering constraint disappears entirely.** Separating the test files inside the same sketch directory is enough.

The same goes for a test that runs for a long time to measure how a resource grows. If you do not want it mixed in with the others, arrange things so it is not mixed in. Making the shape that needs no rule beats writing down a rule that says "this one runs last".

### Two checks

**Run the module once in reverse.** This is the everyday check. It costs one upload and catches all three shapes above. **Reverse the module's tests within a single pytest invocation**; do not run them one at a time in reverse order, which pays an upload per test and turns into the other, more expensive check. **The second one in particular is invisible to running tests alone**, because a test run by itself is always first.

**Its subject is state shared between tests, so it applies for as long as multi-test modules exist.** At one test per module there is nothing left to reverse, and the check stops being worth running as a routine; order dependence has moved inside the merged test, and auditing it there is a separate question, covered further below. **While multi-test modules remain, run it** — in one suite it found defects in most of the modules it was pointed at, and the majority of those showed up neither in a single-test run nor in a normal one. **It is also what makes the move to one test per module safe**, since it tells you which modules were leaning on order before you merge them.

```bash
pytest $(pytest my_app --collect-only -q | grep '::' | tac)
```

**That one-liner does not get along with parametrize.** A node id such as `test_payload[512]` is unquoted, so the shell may treat it as a glob, and a parameter containing a space is word-split. The dependable form is a tiny plugin that only reverses, passed with `-p`, which also keeps your conftest clean.

```python
# revorder.py
def pytest_collection_modifyitems(session, config, items):
    items.reverse()
```

```bash
PYTHONPATH=. pytest -p revorder my_app/
```

**Read the results as three values**, not two: `passed`, `failed` and `error`. **An `error` is an environment failure, not a test failure** — the upload died, the port was missing. Count in two values and you will score environment failures as successes; a real tally script did exactly that.

**When many fail at once, suspect the environment rather than the tests.** A run of consecutive errors is worth stopping for, to check the wiring and the ports.

You can also put it in a `conftest.py` and switch it on when you want it.

```python
def pytest_collection_modifyitems(items):
    items.reverse()
```

**Run them one at a time.** This is the criterion for being able to run a single test with `-k` or a node id. It pays one upload per test, so use it to confirm the rule rather than as the daily check.

```bash
pytest my_app/test_my_app.py::test_count
```

**With either check, the point is to actually run it.** The suspicion that a test only passes because of an earlier test's side effect **cannot be settled by grepping for it.** In practice the misreadings went both ways: a test classified as querying turned out to be reading start-up output, and a test assumed to be waiting for a connection notice turned out to query first. Do not take comfort in a static count. Change the order and run it.

**Running is not sufficient either, and no one route finds everything.** In an audit of restore code, the defects came out by different routes and each route found exactly one of them: the ordinary full run, the reverse run, and re-reading the sketches, which accounted for the rest. The one the reverse run caught appeared neither alone nor in a normal run. The ones reading caught never fired in any run at all, because the test that would have exposed them happened to sit late in its module. **Run the checks, and read the restore paths too.**

**Searching for them mechanically did not work.** A rule of "file-scope variables not assigned in `setup()`" cannot see a callback registration or a value written into a server attribute, because **neither of those is a variable.** A search shaped like a variable cannot find state that is not held in one. And where the state was in a variable, the rule classified it backwards: nothing in the type or the name of a `bool` separates a setting you may restore from a record that something irreversible has happened. Narrowing a large candidate list left a handful, of which one was real.

### A test that passes and fails at random

**This is the worst failure a suite can have.** A test that always fails gets fixed. One that fails sometimes gets re-run, and a suite people re-run is a suite people have stopped believing. One such test devalues every other test around it.

**The usual name for the symptom is a flaky test**, whatever the cause turns out to be. The word describes the report rather than the mechanism, which is exactly why it pays to split it before acting.

**"Race" here means a race condition:** the result depends on which of two things happens first, and nothing decides that order. Whether your read reaches the port before or after the line has finished arriving. Whether the peer has finished starting before the test writes to it. With nothing enforcing the order, **the same test on the same input can come out differently from one run to the next.** A race is not a test that is wrong. It is **a test whose answer is not determined** — which is exactly why re-running it looks like a fix.

**Start by separating three shapes, because they have different causes and different fixes.** Run the same selection twice, changing nothing.

| What you see | Shape | Where to look |
| --- | --- | --- |
| Two runs of the same selection disagree | **Non-deterministic.** Something is timing-dependent | the next paragraph, then the list below |
| Fails in the full run, passes alone, every time | **Order dependence inside the run** | *Three shapes that do not work* |
| Passes now, fails after some other run, and reproduces neither alone nor in reverse | **State left from a previous run** | further down this section |

Only the first is non-deterministic. The other two are deterministic and are already answered elsewhere in this guide; calling them flaky sends you looking in the wrong place.

**And non-deterministic does not always mean a race.** Two runs also disagree when something outside your control took a variable amount of time: associating with an access point, DHCP, a network service coming up. **The question to ask is whether the outcome is determined and merely late, or not determined at all.** An association that succeeds in a variable time is the first kind — **the short timeout was the bug**, so raising it is the fix and not a paper-over. A read that may or may not have the complete line is the second kind, and no timeout value repairs it.

For the environmental kind, a bigger number is most of the answer, and these make it better than only that.

- **Time out generously but keep a ceiling, and name the dependency in the message.** A run that dies after a long wait saying which access point it was waiting for is diagnosable; one that just times out is not.
- **Report it as an environment error, not a test failure**, wherever the connection is a precondition rather than the subject. That is the `error` versus `failed` distinction above — scoring a dead access point as a product failure is how a tally comes to lie.
- **Retry the precondition, never the assertion.** A bounded retry while establishing a precondition is rig robustness. A retry wrapped around the thing under test hides the defect. **That is where the line sits**, not at the word retry.
- **Hoist it out of the per-test path.** If every test re-associates, every test pays the variance.
- **Reduce the variance where you own the rig.** A test-only access point rather than the office network, a fixed channel, credentials pinned in `.env`. This is the only measure that removes the cause instead of tolerating it.
- **Do not assert on elapsed time** unless the connection time is itself the subject.

**What tends to become a race.**

- **A pattern that does not wait for the end of the line.** A serial line arrives in pieces. If the last thing in the pattern is variable-length and is not terminated by the newline, the match settles the moment what has arrived satisfies it, and you read a truncated value. **Whether the whole field is there depends on arrival timing alone**, so the same test can pass, can fail, and — worst of all — **can pass carrying a wrong value.** Terminate the pattern with `\r?\n`; `[^\r\n]*` is not enough, because it also matches zero characters. *Terminate a trailing variable-length field at the end of the line* has the detail.
- **Waiting for something announced once.** If the line can be emitted before you start reading, the test is a race by construction — and `expect` discards what came before its match. **Query the state instead**, which the next section covers.
- **A check that runs after a timed-out `expect`.** The awaited line can still arrive, late, and the next check consumes it and fails on the wrong thing. Stop at the first failure rather than continuing.
- **Asserting after a fixed delay** instead of on an observable condition. It passes on a quiet machine and fails on a busy one.
- **Boot-time interference.** The primary is already running `setup()` while the peer is being flashed, so it can observe the peer's resets. Timing decides whether it does. *Do not affect the outside world at boot* is the fix.
- **A receiver that does not filter what it accepts.** Advertising from a neighbouring device, an infrared frame from somebody else's remote, any traffic your test never sent. It can fail the test, arriving as a malformed frame that you then report as an error. **Worse, it can pass the test**, by satisfying an assertion your own peer never satisfied. Either way the outcome depends on what happened to be in the air during your window, which is why it looks intermittent rather than wrong.
- **Retries.** An unbounded retry converts a hard failure into an intermittent one. It does not fix the defect, it hides it and makes the suite untrustworthy at the same time.
- **Two independently timed sides**, such as both ends of a radio link, where neither waits for the other to be ready.

**A peer is the likeliest carrier of state from a previous run.** The primary is the thing you are watching, and it gets a fresh upload and boot at every module boundary, so its state stays on your mind. A peer's does not, and several kinds of peer state outlive the upload.

- **Pairing, bonding and stored settings live in non-volatile storage**, which an upload does not necessarily erase — the same board-dependence as on the primary.
- **A peer need not be a board you flash at all.** A commercial device, an instrument, a rig shared with another project: nothing resets it between your runs.
- **Radio state can sit in a companion chip** the reset signal never reaches, so the peer's link or advertising can outlive its own reboot.

The result is a test that passes on your bench today and fails on the same bench tomorrow, with nothing in the suite having changed. **A single test is not proof of independence when a peer is involved.**

**Latching state — a *sticky* flag — is the other carrier, and it hides somewhere else entirely.** A status or error bit that stays set once raised until something clears it: a peripheral's overrun or framing error, an accumulated fault register, a counter that only goes up. Two properties make it awkward in a test.

- **It often survives a software reset**, because it lives in a peripheral rather than in your variables. *A reset does not necessarily clean anything* applies directly: the reset reaches only as far as its signal goes.
- **Reading it may clear it**, which turns it into something two readers compete for. If a log audit consumes it, the test cannot see it. If one check consumes it, the next check reads zero. **A read-to-clear flag is not an observation, it is a withdrawal.**

So an assertion of "no errors" can come out either way depending on who read the register first and on what happened several tests earlier. **Clear it at the start of the test, and treat reading it as consuming it.**

**Prevention, in the order that pays.**

- **Establish the premise on both sides, inside the test.** Rebuilding the primary's state and trusting the peer's is the common half-measure. The peer needs the same treatment.
- **Normalize at the start, not only at the end.** Cleanup is skipped by an early exit; the start of a test always runs. Anything that survives a run has to be cleared where it is certain to be cleared.
- **Assert on observable conditions, never on elapsed time.** Timeout generously. Retry only while building a precondition, never around an assertion.
- **Use a test-only identifier** so a neighbouring bench cannot satisfy your assertion for you, and narrow the acceptance at the receiver rather than after the fact. **Confirm it by running the test with the peer switched off: if it still passes, you are not filtering.** That check costs one run and it is the only thing that distinguishes a test that verifies your device from one that verifies the room.
- **Stop on the first failure**, so a broken state cannot produce a second, unrelated symptom.

**You cannot show a race is fixed with one green run.** Run the same selection repeatedly and require it to agree with itself. And if you cannot make it deterministic, consider that the test may be reporting a race in the product. **That is a finding, not a nuisance.** Do not paper it over with a longer timeout — and note that this is the opposite of the environmental case above, where a longer timeout is exactly the right answer. **The two look identical in the report and are treated in opposite ways**, which is why the two-run triage comes first.

### Query the state instead of waiting for an announcement

Shapes 2 and 3 both disappear with one change. **Stop waiting for a line printed once at boot, and give the sketch a command that reports the current value at any time.**

```cpp
  else if (line == "state?")
  {
    Serial.print("STATE conn=");
    Serial.println(connected ? 1 : 0);
  }
```

The test asks for it. Whatever position it runs in, an answer comes back.

**Merging into one larger test removes the symptom; querying removes the cause.** Merging fixes the order by freezing it, but the dependency is still there. Querying makes the test work in any order.

### Being able to stop and start widens what you can fix

A test asserting a state that only holds right after boot fails as soon as another test runs first. That is a design error, but **you cannot fix it without a means to.** There is a real case of someone concluding "no command exists to put the host back, so the order has to live inside the test" and merging two tests. Merging only pins the order; the dependency is still there.

If the device can be stopped and started again, that state can be rebuilt at any time. Stop at the top of the test, start again, wait for the enumeration or the connection, then assert. The dependency on order disappears and the one-test-per-module shape survives.

```text
stop -> start -> wait until ready -> assert
```

**This shape assumes the stop actually clears that state.** Some libraries keep a cache or a registration across a stop, and copying the shape will not fix anything there. **Confirm from the device log that the stop really cleared it.** Do not assume what a library's stop discards.

Stop and start commands usually exist for a different reason, to avoid affecting the outside world at boot. **Machinery added to close the flashing window turns out, as a by-product, to be the means of fixing order dependence.** Gating does not only make the error findable through the reverse-order check; it makes the error fixable.

The price is the time to rebuild: whatever enumerating or reconnecting costs. It is still cheaper than a reverse-order check that stays red forever.

**This cost is not the same as the stop and start that closes the flashing window.** That window opens once per module, so that one is paid once. This one is **paid once for every test that needs a pristine state.** Do not conflate them.

**Before concluding that merging is the only option because nothing can put the device back, check whether you can build that means.** A merge is usually the result of skipping that check.

### Get granularity from the device side

Splitting tests gives you the name of what broke, but the device can give you the same thing. The sketch runs several checks, prints the results and the counts, and one pytest test reads that. One upload, one connection, and the sketch names the check that failed.

```text
TEST_END pass=37 fail=0
```

**This form has a limit.** It can only judge what the device knows. **Evidence that exists only on the host cannot be judged there**: what the other side parsed out of a descriptor, which endpoint addresses it assigned, and so on. Keep those checks on the host side.

Note that needing the device to present itself differently per case is not a reason to abandon the form. A device can re-enumerate without being reflashed, so one sketch can rebuild itself as something else. That costs enumeration time, not an upload.

### What splitting buys is less than it looks

Whether merging is faster is unknown until you measure. In one suite, where fixed cost is a small share of each test, neither merging nor splitting moved the total. If time does not decide, the benefits have to. Lay them out, and every item turns out to be better served some other way.

- **The name tells you where it broke.** **You do not have to give that up.** Keep each case as a named function and call them in order: the traceback names the failing frame after the case, so a merged test still says which case broke, and each case keeps its own docstring. What merging really costs is a line in the result list, not the name. **If per-check records are what you want, reporting from the device is more reliable.**
- **You can run just one.** To carve out a slow piece of verification, **splitting the module fits better.** Two test files in the same sketch directory become two modules, each with its own upload, so the state is independent too. But **every module you split off runs both the compile and the upload again.** The compile can be faster than the first thanks to the incremental build, but it is not free. A module per case is expensive, so carve out only the heavy ones.
- **One failure does not stop the rest.** This one is unique to splitting. On hardware, though, the failure leaves the board in a bad state. What follows is not just unreliable: **the next test sees the half-finished state and unrelated failures pile up.** One suite had exactly that happening until cleanup was added. Continuing can do harm rather than good.

**The reverse-order check also only exists once you have split.** That one can be a reason to split, and the next section covers it.

**And the rule buys one thing that no timing measurement can argue against: the restore code you never write.** With one test per module nothing carries over inside the module, so cleanup only ever has to stop things, never put the board back the way it booted — see *What to stop*, where that turns out to be the half the bugs live in. Even in the suite above, where merging moved the total not at all, this reason still held.

So **there is almost no positive reason to put several tests in one module. Treat one test per module as the rule.** When you want to split, first ask whether the module can be split instead, or whether reporting from the device would do. If you split anyway, the added time is governed by the formula further below.

### Break a large test into functions

**Once a test has grown large, split it into functions.** Not into more tests — into named functions inside the one test. Each function holds one feature's worth of checking, so the test body reads as a list of what it verifies, and you can work on one piece without carrying the rest in your head. **This is ordinary structuring, done for readability**, and it applies the same whether the test grew on its own or arrived that size from merging a module.

```python
def test_msc(dut):
    def capacity():
        dut.expect_exact("MSC_CAPACITY ok=1 blocks=16 block_size=512")

    def readback():
        dut.expect_exact("MSC_READ ok=1")

    for check in (capacity, readback):
        check()
```

**Either shape works.** Nested functions close over `dut` and take no arguments. Module-level functions named `_case(dut, peers)` take them explicitly and keep the file flat; that form **converts mechanically** — rename `def test_x(` to `def _x(` and generate the calls — so merging an existing module does not mean rewriting any bodies, and every case keeps its docstring.

**A case has to return the board in the state it found it.** Between modules that is guaranteed for you: each module starts with an upload and a boot. **Between cases nobody guarantees it.** Merging is precisely the act of removing that guarantee from the boundaries inside the module, so each function now owes what the upload used to do on its behalf. Two shapes come up, and this guide already answers both.

- **A case that leaves the board unusable** — it ends the link, or disables something until reset. **Move it out into its own module**, the same answer as for a destructive test, applied at case granularity.
- **A case that deliberately leaves something switched off** — a callback removed to show the code copes without it. **Have the case put it back**, which usually costs one more command in the sketch and one more line at the end of the case.

**Then the rule that matters: do not catch the failures.** Drive the functions from a list, call them in order, and let a failure propagate on its own.

**The traceback is the reason.** Left uncaught, pytest names the failing frame after the check and shows the line and the value it was waiting for.

```text
test_usb_msc.py:61: in capacity
    dut.expect_exact("MSC_CAPACITY ok=1 blocks=16 block_size=512")
```

Catch it and all of that collapses into whatever one-line summary you wrote by hand. **Catching discards the evidence and then asks you to rebuild a worse copy of it.**

There is a second cost, specific to serial. **A check that timed out left the line it was waiting for unread.** If that line arrives late, the next check reads it and fails on the wrong thing, so continuing means draining the buffer between checks. That is complexity paid to arrive somewhere worse than stopping would have.

This is the same conclusion as **One failure does not stop the rest** above, reached from the other side: once a check has failed on hardware the state is no longer trustworthy, and what follows is noise rather than information.

**Driving from a list is not decoration.** Merging moves order dependence inside the test, so the reverse-order check has to move inside with it. A list can be reversed; a sequence of direct calls cannot.

**But not every merged test is a candidate for that.** Ask whether each function establishes what it needs. If it does, the list is auditable and reversing it is a real check. **If a step only means anything after the one before it, the order is the subject matter rather than an accident.** A protocol conversation is the clear case: set a group of fields and read them back, then set one field on its own and assert the others still hold what the previous request left. Reversing that asserts a state nobody established. **That is one case with several assertions, not several cases** — give it functions for readability and leave the reversal off. Offer a reversible list where reversal is meaningless and someone will add the fixture, watch it fail, and conclude the test is broken.

**Listing them is already a detector, before you run anything.** Arranging the calls into a list makes you ask, one case at a time, what that case leaves behind — a question a straight run of calls never puts to you. In one suite that step alone surfaced two order dependencies in a module that passed forward and passed alone.

```python
import os

import pytest


@pytest.fixture
def run_checks():
    def _run(checks):
        order = list(checks)
        if os.environ.get("REVERSE_CHECKS") == "1":
            order.reverse()
        for check in order:
            check()

    return _run
```

**Compare against the exact value, as above.** A switch read as "set to anything" turns one leftover line in a shell profile into a permanently reversed suite, which is worse than having no switch: every run is the audit and none is the ordinary check.

**And test the switch itself.** If the reversal stops reversing, the audit quietly becomes a second forward run. That is covered below, with the other checks that go silently green when they break.

### When splitting really is required

Almost never, in truth. In one suite where the multi-test modules were counted and examined, **most of them had no reason beyond having been written that way.** Even so, two things are lost for good once you merge. Both have the same shape: wanting to attach something per case.

**First, repeating over values can be written inside a test.** Trying a range of payload sizes needs no extra tests. **Here, and only here, collecting the failures and asserting at the end earns its keep:** every iteration runs the same line, so the traceback cannot say which value failed. Collecting is what records the value at all. A sequence of differently-named checks is the opposite case, covered just above.

```python
def test_payload(dut):
    failures = []
    for size in (1, 64, 512):
        dut.write(f"send {size}\n")
        try:
            dut.expect_exact(f"SENT {size}", timeout=5)
        except Exception:
            failures.append(size)
    assert not failures, f"failed sizes: {failures}"
```

**Stop early if a failure leaves the device unusable.** Collecting assumes the next value still means something. Where a failed operation leaves the board in a state the values after it cannot be trusted in, break out of the loop instead. Collecting is a convenience here, not a rule.

**1. When something has to be attached per case.** This is the real dividing line. A loop cannot mark one of its values, nor select one of them to run.

- **pytest markers.** `xfail` for a known bug, `slow` for the heavy one, `skipif` for an environment dependency. You cannot mark part of a test.
- **Selection with `-k` or a node id.** Running one specific value to investigate it is not something a loop offers.
- **Project-specific machinery keyed on node id**, such as a conftest that audits serial logs and holds an allowlist of lines permitted for one particular case.

The third has a real instance. In a module of many operations, exactly one legitimately provokes an error line that the specification allows. Keyed per case, only that one is permitted. **Merge the module and the permission has to widen to cover all of it, so the same line goes unnoticed where it should not be allowed.**

When a value-driven repetition needs this, use `@pytest.mark.parametrize`. **The compile and the upload still happen once per module**, each value becomes an independent test named like `test_payload[512]`, and markers can be attached per value.

**But parametrize is board-dependent too.** On a board that resets on every connection, you re-run the boot once per value, and re-establish per-value state on top of that. Where closing the connection ends the process, as with a host core, the second case cannot even connect. **Repeating over values alone can be written as a loop, so look at how your board behaves before choosing.**

```python
import pytest


@pytest.mark.parametrize("size", [1, 64, 512])
def test_payload(dut, size):
    dut.write(f"send {size}\n")
    dut.expect_exact(f"SENT {size}")
```

But **finer is not automatically better.** That same allowlist also had an entry written broadly on purpose, for a transient that lands on a different case every run: a property of the run, not of any one case. **Match the key to the actual scope of the thing.** And if your implementation stops at the first matching rule, **put the specific rules ahead of the broad ones**, or a broad rule will swallow a specific one.

**2. When you want to find assertions that pass for the wrong reason.** This differs in kind from the other one: it is about the quality of the tests rather than of the product.

The reverse-order check only means anything **where state is shared**, and state is shared only inside a module. All three alternatives destroy the check.

- **Merge into one test.** The order assumptions move into the test body, out of the check's reach — **unless you move the audit in with them.** Drive the checks from a list the test can reverse, as above, and the check survives the merge. That is machinery you have to write and keep, so weigh it against simply not merging.
- **Split into modules.** Every module begins with an upload and a boot, so the premise always holds and the check runs empty.
- **Report from the device.** The order is fixed in firmware; reordering means reflashing.

And what the check finds is not only order dependence. It also finds **assertions satisfied by the state the board happened to be in rather than by anything the test established.** In one real case, an assertion that the discovery phase does not start using a device held only because it ran right after boot. **It was not an empty assertion** — a regression that made discovery start using one would still have failed it — but it was satisfied by the boot state, so putting any test that connects a device ahead of it made it fail as a false positive. Rewritten to establish its own premise, by stopping, starting, waiting and only then asserting, it holds no matter what ran before.

Take any of the alternatives and such an assertion stays in place, silently, and always green.

**An assertion that cannot notice a broken reporting path is a separate class, and the reverse-order check does not find it.** Establishing the premise does not fix it either. If the sketch came to print zero unconditionally, an assertion that a counter is zero stays green forever, because **nothing in the test shows that the counter can move at all.**

**Most of the suspects are not it, though.** Sweep a suite for "asserts zero and never observes non-zero" and the list comes back long. Three things account for nearly all of it, and none of them is a defect.

- **It is a hygiene check, not an assertion.** A zero read at the start of a test says "nothing is left over from the last run". The environment satisfying it is the normal case; its failing is precisely the signal you wanted. **Only a claim about the product needs to be able to fail on the product.**
- **Another check in the same test observes the value moving.** It does not have to be the same case. Merging puts sibling checks inside one test, and a sibling that sees the field non-zero is evidence enough that the field can move.
- **The line encodes the value redundantly.** Where a field is derived from the same call as its neighbours, a reporting path stuck at zero would have to fake the correlation as well. Fields printed together from one query, or a `submitted` / `completed` / `errors` triple where a dead error tally makes the other two disagree, are already protected. **Check for this before rewriting anything:** a redundantly encoded report buys what dirtying and restoring buys, for free.

Where none of those hold, the remedy is structural: **make the value move inside the same case.** Dirty the state, confirm it changed, restore it, then assert the pristine value. A dead reporting path then fails at the confirmation step instead of passing at the end.

**Expect this class to be rare.** Across two suites audited this way, order dependence turned up several times over while this turned up once. **And the sweep cannot be finished statically.** An audit that collects `expect` patterns out of the source cannot see a pattern passed in through a variable, which in one run was the single largest group of false positives. Static screening narrows the list; only reading decides.

**When you have finished suspecting the product's assertions, turn the same eye on the checks.** A check is code, and this class of defect applies to it too. Let the reversal in a `run_checks` fixture stop reversing and the reverse audit becomes a second forward run: every module passes, the audit reports success, and nothing was examined. **A reverse run passing is not evidence that it reversed**, because it passes either way. A single-test audit and a serial-log audit have the same shape — broken, each one goes silently green.

**The tell is whether that check has ever reported a failure.** Where it has, the record is your evidence and you need nothing further. Where it has not, either break it deliberately and confirm it complains, or **assert the mechanism directly**, which is the cheaper option. A test that the check list comes back in the order you asked for needs no device at all, so it lives in a directory with no `.ino` and costs nothing to run. Assert the ordering both ways, and assert that a failure still propagates — that last one turns the do-not-catch rule into something a future change cannot quietly undo.

In short: **several tests are not required for expressiveness. They are required for detection.**

**Economics is not a reason.** "Rebuilding per case is cheaper than uploading per case" is true, but it is a comparison against several modules. Merging into one test costs about the same, so economics never argues for several tests.

**"Only this case needs a different environment" deserves checking before you say it.** In one instance, four tests believed to need a separate profile all passed on the same profile once the feature they depended on had shipped. Reasons of this shape can evaporate on inspection.

### Hoist heavy setup out of the per-test path

The time that splitting adds is governed by this.

```text
added time = (number of tests - 1) x measured per-test setup and cleanup
```

**Before you compare two timings, check what else was running.** A measurement taken while an unrelated build occupies the machine is not a measurement. The way to tell is to **look at a module you did not touch**: if that moved by a similar amount, the comparison is void, whatever the numbers say about the parts you did change. One team nearly reported that merging had made things slower, when compile-dominated modules had all drifted up by a comparable amount, an untouched one included.

Argue about splitting versus merging without measuring the second factor and you will not reach an answer. **"It is slow because there are many tests" is a misdiagnosis. It is slow because per-test setup is heavy.** The very same act of adding one test costs wildly different amounts depending on the arrangement: reconnecting and nothing else is not remotely comparable to stopping and restarting radio or USB every time.

**"That mechanism is expensive" and "paying for that mechanism every time is expensive" are different statements.** In practice, paying for the machinery that closes the flashing window on every test stretched the run substantially, while moving it to once per module produced the same cleanliness in nearly the same time as not having it at all. **Almost all of the added time came from where it sat, not from the feature itself.** When something feels expensive, suspect its placement first.

**When it turns out to be heavy, the fix is to hoist it, not to merge.** Merging does make it faster, but the cost comes back once per module: twenty modules pay it twenty times. Move the setup out of the per-test path and the saving holds regardless of test count. **Try hoisting first, and consider merging only if that is not enough.**

**Hoisting is not only about the start.** Make the start idempotent and it still buys nothing **if the teardown stops the thing on every test**: by the next test the stop has already happened, so the idempotence check never fires and the whole cost is paid again. In one real case the start had been written idempotent from day one and the cost remained in full. **If making the start idempotent did not make it faster, look at whether the stop runs every test.**

There are two ways to hoist the start.

**Make it idempotent on the device.** Write the start command so that later invocations do nothing. Nothing has to be tracked on the Python side, which makes this the simpler of the two.

```cpp
  else if (line == "begin")
  {
    if (!started)
    {
      started = true;
      // the actual start-up work
    }
    Serial.println("BEGUN");
  }
```

**Do it once from Python.** Guard the work with a per-module flag.

```python
@pytest.fixture(autouse=True)
def start_once(request, dut, peers):
    if not getattr(request.module, "_started", False):
        request.module._started = True
        dut.write("begin\n")
        dut.expect_exact("BEGUN")
    yield
```

**The stop side needs a decision about when.** There is nothing to make idempotent, so the trick used for the start does not apply. If the window opens once per module, stop once, after the module's last test.

```python
@pytest.fixture(autouse=True)
def usb_host(dut, peers, request):
    dut.write("begin\n")          # idempotent on the device: a no-op after the first
    yield
    items = [i for i in request.session.items if i.module is request.node.module]
    if not items or request.node is items[-1]:
        dut.write("stop\n")
        dut.expect_exact("STOPPED")
```

**The fixture scope is constrained.** `dut` and `peers` are function-scoped, so **a fixture that requests them cannot be module-scoped.** Setup fails outright. That constraint is why the guard above uses a flag.

```text
ScopeMismatch: You tried to access the function scoped fixture peers
with a module scoped request object.
```

**Ordering has a trap too.** An autouse fixture that starts something **runs before the peer upload unless it takes `peers` as an argument.** Take it for the ordering alone, even when you never use the value. Forget it and the start happens while the peer is being flashed, so whatever you put in place to avoid exactly that never takes effect. In the log you see the start recorded, immediately followed by errors caused by the flashing.

## Principles for peer tests

Policies that have held up for tests with two or more boards.

- **Narrow the partner down with a test-only identifier.** For BLE, use a test-only 128-bit service UUID to exclude the devices around you. Do not decide who to connect to from the device name alone.
- **Make pass or fail decidable from the serial logs of both sides.** Guessing from one side leaves you unable to tell which side is at fault.
- **Stop scanning, advertising, subscriptions and connections at the end of every test.**
- **Allow a timeout for transient radio delays, but do not retry without limit.** Unlimited retries hide defects.
- **Cross-check the disconnect reason, the MTU and the security state on both sides** wherever you can.
- **Where possible, make one side a direct implementation over the standard library.** Two copies of your own library cannot demonstrate interoperability.
- **For tests that carry state, state the state at start and at end explicitly.** This matters most for things that survive a run, such as pairing information and non-volatile storage.

## Do not affect the outside world at boot

With peers, the flashing order needs care. The primary upload runs first, at module level, and the peer upload runs during the first test's setup. In other words, **the peer is flashed after the primary has booted and run `setup()`**.

If the primary brings up radio or USB in `setup()`, it can observe the resets and enumerations caused by flashing the peer, and record them as errors. That is not a defect in the sketch.

The fix is to **start nothing that affects the outside world in `setup()`, and start it when the test says so**. Enable it on the first line of the test body, by which point the peer has already been flashed.

That shape brings two problems of its own. Both happen on real hardware.

### The reply to the enabling command swallows the start-up output

Send the enabling command and wait for a reply with `expect`, and **anything printed before that reply falls behind the read position.** `expect` reads forward to the match and discards what came before it. Connect lines and enumeration dumps the sketch printed while starting are then invisible to the rest of the test. It looks as though the sketch never printed them, which makes for a failure that is hard to trace.

| When the sketch prints it | Can the test `expect` that line? |
| --- | --- |
| Before the reply | No; it fails on a timeout |
| After the reply | Yes |

So **print the start-up output after the reply.** Only the order changes; what the sketch does need not.

### When to answer is a real choice

Whichever way you lean, answering has a failure mode.

- **Answer as soon as the peripheral is started.** The test body begins running before anything is enumerated or connected. Writing to the other side goes nowhere.
- **Answer only once it is genuinely usable.** Then, per the section above, the start-up output precedes the reply and is swallowed.

**Only one shape satisfies both.** Defer the answer until it is usable, and **re-emit the start-up lines after answering.** Tests that move data need the device live; tests that watch the lifecycle need the connect line visible. When one sketch carries both kinds of test, this is the shape you need.

Projects that use everything covered here are collected in [Example Projects](TESTING_EXAMPLES.md).
