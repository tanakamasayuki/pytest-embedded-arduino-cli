# FAQ

[日本語](TESTING_FAQ.ja.md)

This index is organized by symptom or question. Each entry gives a short answer and points to a more detailed guide when useful. If the entry solves the problem, there is no need to follow the link.

## Collection and startup

### `import file mismatch`, and the run stops before any test

Two test files share a basename. pytest imports test modules by basename, so the second one collides with the first. **Basenames must be unique across the whole project**, even in different directories, and even for files that never run together.

→ [Advanced Testing](TESTING_ADVANCED.md), *How tests are collected*

### A test is not picked up, or a fixture never seems to run

A test function needs the `test_` prefix. In the other direction, **a fixture whose name starts with `test_` still works as a fixture, but pytest silently leaves it out of collection** with no warning, so it can look as though nothing happens.

→ [Advanced Testing](TESTING_ADVANCED.md), *How tests are collected*

### `PluginValidationError: unknown hook`, and pytest will not start

A `pytest_*` function in a `conftest.py` is misspelled. Hook names are fixed, and pytest refuses to start rather than quietly ignoring one it does not know. Neither pytest-embedded nor this plugin adds hook names of its own; **the names are pytest's alone.**

→ [Advanced Testing](TESTING_ADVANCED.md), *What conftest.py is*

### Every test warns about `record_xml_attribute`

`PytestExperimentalApiWarning: record_xml_attribute is an experimental feature`, once per test, with the line number pointing at your own test function. **It is not your test.** pytest-embedded's `app_path` fixture requests pytest's `record_xml_attribute`, and pytest marks that API experimental. There is nothing to fix, so silence it.

```toml
# pyproject.toml
[tool.pytest.ini_options]
filterwarnings = [
    "ignore:record_xml_attribute is an experimental feature:pytest.PytestExperimentalApiWarning",
]
```

The same setting in a `pytest.ini` is a newline-separated list, without the brackets and quotes.

```ini
# pytest.ini
[pytest]
filterwarnings =
    ignore:record_xml_attribute is an experimental feature:pytest.PytestExperimentalApiWarning
```

→ [Advanced Testing](TESTING_ADVANCED.md), *Config files: pytest.ini and pyproject.toml*

## Project files and Git

### What should Git track and ignore?

Commit the inputs needed to reproduce a test, and ignore machine-specific settings and output that can be regenerated.

**Normally commit:**

- `pyproject.toml`: direct Python dependencies and pytest settings
- `uv.lock`: resolved Python dependency versions
- `.python-version`: when the project standardizes its Python version
- `sketch.yaml`: board profiles and core and library versions
- `.ino`, `.h`, `.cpp`, and `test_*.py`: the sketch and tests
- `.env.example`: an example without secrets or real port values

**Normally add to `.gitignore`:**

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.env
.pytest-results/
.pytest-embedded/
ardutest/
**/build/
```

`**/build/` contains Arduino CLI compile output and can be regenerated per profile. `.pytest-results/` contains `--save-state` data, `.pytest-embedded/` is the serial-log root when using `--root-logdir=.pytest-embedded`, and `ardutest/` contains ArduTest artifacts. The default serial logs live in the system temporary directory outside the repository and therefore do not normally appear as Git candidates.

Commit `uv.lock` for a project-specific test workspace when reproducible CI is the goal. A library that deliberately tests compatibility across a range of Python dependency versions may also have separate jobs that run without the lock. Merely ignoring the lock does not create that coverage, so keep reproducibility tests and dependency-range tests explicit.

`.env` may contain Wi-Fi credentials as well as real serial ports. Never commit the real values; share only the required variable names through `.env.example`. Adding an already tracked file to `.gitignore` does not remove it from history. If credentials were committed, check the repository history and rotate the credentials as well.

→ [Your First Test](FIRST_TEST.md#2-create-a-python-workspace), `.gitignore` example

## Build and upload

### `sketch.yaml not found` or `multiple .ino files found`

The directory containing the test file is the sketch directory. Use the same layout as an Arduino IDE project: one primary `.ino`, supporting `.h` / `.cpp` files, and a `sketch.yaml` in that directory or an ancestor.

→ [Testing Basics](TESTING_BASICS.md), *Directory layout*

### pytest asks for a profile, or skips the profile I selected

The primary profile comes from `--profile`, `default_profile`, or automatic selection when there is exactly one profile. Multiple unselected profiles are an error. A selected profile absent from that sketch's `sketch.yaml` is an unsupported combination and is skipped before build.

Peers do not automatically select their only profile. Set `default_profile` in `peer_<name>/sketch.yaml` or pass `--peer-profile <name>:<profile>`.

→ [README](README.md), *Peer DUT*

### Every test is skipped with `--run-mode=build`

This is expected. Build mode compiles the sketches but does not execute pytest test functions, so each item reports `skipped test execution in build-only mode`. If compilation succeeded, the build goal succeeded.

→ [README](README.md), *Usage*

### `--run-mode=test` cannot find the build output directory

Test mode skips compilation and reuses a build for the same sketch and profile. Run `--run-mode=all` or `--run-mode=build` first. Switching profiles also switches the build directory.

→ [README](README.md), *Usage*

### A test that needs no hardware still triggers a build

The trigger is **an `.ino` in the same directory**, not whether the test asked for `dut`. Move hardware-free tests into a directory with no sketch and the plugin does nothing for them.

→ [Advanced Testing](TESTING_ADVANCED.md), *The layers of a plan*

### It built yesterday and fails today, after bumping the core or a library

First separate two failures. If Arduino CLI cannot find the declared version, its local package or library index may be stale; run `arduino-cli core update-index` and `arduino-cli lib update-index`. If the version resolves but compile fails, reuse of the previous build may be working against the upgrade, so rerun with `--clean`. Before a release, refresh the indexes and run the full suite with `--clean`.

→ [Advanced Testing](TESTING_ADVANCED.md), *The layers of a plan*

### A newer core version resolves locally but not in GitHub Actions or Docker

When CI reuses Arduino CLI's data directory or an old Docker image, it also reuses the package index stored there. After `sketch.yaml` moves to a newer core, that stale index does not know the release exists and platform resolution fails.

Refresh the indexes **after** restoring caches and **before** starting pytest or any build. Refresh the library index too in jobs that may update library versions.

```yaml
- name: Update Arduino indexes
  run: |
    arduino-cli core update-index
    arduino-cli lib update-index

- name: Run build tests
  run: uv run pytest examples/01_basic --profile=uno --run-mode=build
```

Running `core update-index` only while building a Docker image is not enough if CI keeps using that old image. Refresh it after the job or container starts, or regularly rebuild the base image. Reusing downloaded cores is fine, but **having a core cache and having a current index are separate conditions.**

→ [Advanced Testing](TESTING_ADVANCED.md), *Build tests grow with the product, not the sum*

### The upload fails, or the port cannot be opened

Three shapes, and which one you get says where to look. No port configured gives a `ValueError` when the connection is set up. A port that resolves with nothing behind it fails inside `arduino-cli upload`. A path that does not exist gives a `FileNotFoundError` at connect. A symlink in `.env` makes the middle one easy to hit, because **the string resolves while the device is absent.** The primary is never skipped for this; only peers are.

→ [Advanced Testing](TESTING_ADVANCED.md), *The plugin takes care of peer boards*

### Opening a serial port on Linux fails with `Permission denied`

First check the device file's owning group and the current user's groups.

```bash
ls -l /dev/ttyACM0
id
```

On Debian or Ubuntu, when the device belongs to `dialout`, add the user to that group:

```bash
sudo usermod -aG dialout "$USER"
```

The new group does not apply to an already open login session. Log out and back in, then verify it with `id`. Group names vary with the distribution and udev rules, so use the group shown by `ls -l` rather than assuming it is always `dialout`. Do not use `sudo chmod 666 /dev/ttyACM0` as a permanent fix: reconnecting usually resets it, and it grants unnecessarily broad access.

Testing hardware from Docker also requires passing the device into the container in addition to fixing host permissions. First verify that the corresponding device file is visible inside the container.

### The serial port name changes after upload and the test cannot connect

On boards with native USB, the bootloader and running sketch may enumerate as different USB devices. A port can therefore change from a name such as `/dev/ttyACM0` before upload to `/dev/ttyACM1` afterward. Compare `arduino-cli board list` before and after upload and, on Linux, inspect `/dev/serial/by-id/`.

When the upload and runtime paths are known to differ, specify both:

```bash
uv run pytest tests/my_app \
  --profile=uno \
  --flash-port=/dev/ttyACM0 \
  --port=/dev/ttyACM1
```

`--flash-port` is passed to `arduino-cli upload`, while `--port` is used for pytest serial communication after upload. A `/dev/serial/by-id/...` path can avoid number changes when the board keeps the same USB identity. If the bootloader and sketch expose different identities, specify their respective paths.

### The run waits for a long time after compile and before upload

Another pytest process may hold the device lock for that physical device. The default wait is up to 300 seconds. Check parallel pytest runs and adjust `--device-lock-timeout` if needed. A leftover lock file alone does not keep the device locked; the OS releases the file lock when its process exits.

→ [README](README.md), *Main options*

## Talking to the device

### Serial output is garbled

The baud rate in the sketch's `Serial.begin(...)` differs from pytest's baud rate. The default is 115200. Match the sketch or pass `--baud`.

→ [Testing Basics](TESTING_BASICS.md), *How it works*

### `expect` times out for a line the sketch definitely printed

`expect` reads forward to its match and **throws away everything before it.** A line that went by before an earlier match can never be expected afterwards. Have the sketch emit its start-up output after the reply, not before.

→ [Advanced Testing](TESTING_ADVANCED.md), *Traps in expect*

### The sketch prints `READY`, but the first `expect` times out

The startup-only `READY` may have passed before pytest opened the serial port. This is especially likely while another peer is still uploading. Prefer a handshake that lets pytest query readiness and resend until the device answers.

→ [Testing Basics](TESTING_BASICS.md), *The device does not answer at the start of a test*

### I want to watch serial output during the run and inspect it afterward

Pass `-s` to watch serial output received from the board in the console while the test runs.

```bash
uv run pytest tests/my_app --profile=uno --port=/dev/ttyACM0 -s
```

`-s` controls the live display. Serial output is still collected and saved to `dut.log` when `-s` is present. A normal run without `-s` also collects and saves the serial log; it simply does not show the stream live in the console.

By default, the log root is `pytest-embedded/` inside the system temporary directory. A typical Linux layout is:

```text
/tmp/pytest-embedded/<run timestamp>/<test name>/dut.log
```

The temporary directory varies with the operating system and environment settings such as `TMPDIR`, `TEMP`, and `TMP`, so it is not always `/tmp`. Use `--root-logdir` when you want a predictable location.

```bash
uv run pytest tests/my_app --root-logdir=.pytest-embedded
```

For saved contents and platform-specific locations, see:

- [README: Log Directory Summary](README.md#log-directory-summary)
- [Advanced Testing: Where logs and artifacts live](TESTING_ADVANCED.md#where-logs-and-artifacts-live)

### The end of `dut.log` is missing or cut mid-line

If the test ends at its last match, the connection may close before later received bytes reach the log. Have the device emit an end marker and `expect` it, or wait for `pexpect.TIMEOUT` at the end to drain the remaining output.

→ [Advanced Testing](TESTING_ADVANCED.md), *Where logs and artifacts live*

### A value captured by a regular expression is truncated

A variable-length pattern at the end can match before the rest of the line arrives. Include an end such as `\r?\n` after the capture so the match waits for the complete line.

→ [Advanced Testing](TESTING_ADVANCED.md), *End variable-length fields at the line boundary*

### The second test in a module cannot connect, on a host core

Closing the connection ends the executable, so there is nothing left to connect to, and `parametrize` fails for the same reason. **On a host core, one module is one test.** Split the module rather than the test; with no flashing and no board to share, a module is cheap there.

→ [Testing Basics](TESTING_BASICS.md), *Zero boards: run on a host core*

### The board still holds the previous run's state, even though it was flashed

Whether an upload erases non-volatile storage **depends on the board**, and by default it often does not. Either clear it from the sketch at the start of the test, or use a full-erase-on-upload setting where the platform offers one — not every platform does, and each spells it differently.

→ [Testing Basics](TESTING_BASICS.md), *session, module, test*

### The board keeps advertising, or a pin keeps driving, after the run

Nothing stops it unless you stop it. Put the stop in a fixture so it runs on an early exit too. **Do not assume a reset cleans up:** how far a software reset goes is board-dependent, it reaches only as far as the reset signal does, and it re-runs `setup()`, which can put the state straight back.

→ [Advanced Testing](TESTING_ADVANCED.md), *Cleaning up after an early exit*

## Test plan

### A test passes alone but fails in the full run, or the other way round

**If it is consistent both ways**, it depends on something an earlier test did. Three shapes account for most of it: riding on state an earlier test accumulated, depending on being first, and assuming a pristine state that another test dirties. **Fix the dependency, not the order** — pinning the order hides a design error rather than removing it.

→ [Advanced Testing](TESTING_ADVANCED.md), *Three shapes that do not work*

### The same test passes sometimes and fails sometimes

**Separate three shapes before hunting.** Run the same selection twice, changing nothing. Two runs that disagree mean a real race — a fixed delay, something announced once, a check after a timed-out `expect`, or a retry papering over a failure. Two runs that agree mean it is deterministic after all: either order dependence inside the run, or **state left behind by a previous run.** The last one reproduces neither alone nor in reverse, and **a peer is its likeliest carrier** — pairing data outlives the upload, and a peer may be a device nobody resets at all.

→ [Advanced Testing](TESTING_ADVANCED.md), *A test that passes and fails at random*

### A peer test is skipped and I did not ask for that

A peer whose port or profile cannot be resolved is skipped, with the reason printed. That is deliberate: the same test files then work both on a bench that has the extra board and on one that does not.

→ [Advanced Testing](TESTING_ADVANCED.md), *The plugin takes care of peer boards*
