# FAQ

[日本語](TESTING_FAQ.ja.md)

A symptom-first index into the other guides. Each entry says what causes it and points at the section that explains it in full. Nothing here is new material — if an entry is enough to unblock you, you do not need to read further.

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

## Build and upload

### A test that needs no hardware still triggers a build

The trigger is **an `.ino` in the same directory**, not whether the test asked for `dut`. Move hardware-free tests into a directory with no sketch and the plugin does nothing for them.

→ [Advanced Testing](TESTING_ADVANCED.md), *The layers of a plan*

### It built yesterday and fails today, after bumping the core or a library

Reuse of the previous build is what makes an ordinary run fast, and a version bump is exactly when that reuse turns against you. Re-run with `--clean`. **This is the usual reason to reach for it**, and a full test with `--clean` before a release is worth the wait.

→ [Advanced Testing](TESTING_ADVANCED.md), *The layers of a plan*

### The upload fails, or the port cannot be opened

Three shapes, and which one you get says where to look. No port configured gives a `ValueError` when the connection is set up. A port that resolves with nothing behind it fails inside `arduino-cli upload`. A path that does not exist gives a `FileNotFoundError` at connect. A symlink in `.env` makes the middle one easy to hit, because **the string resolves while the device is absent.** The primary is never skipped for this; only peers are.

→ [Advanced Testing](TESTING_ADVANCED.md), *The plugin takes care of peer boards*

## Talking to the device

### `expect` times out for a line the sketch definitely printed

`expect` reads forward to its match and **throws away everything before it.** A line that went by before an earlier match can never be expected afterwards. Have the sketch emit its start-up output after the reply, not before.

→ [Advanced Testing](TESTING_ADVANCED.md), *Traps in expect*

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

It depends on something an earlier test did. Three shapes account for most of it: riding on state an earlier test accumulated, depending on being first, and assuming a pristine state that another test dirties. **Fix the dependency, not the order** — pinning the order hides a design error rather than removing it.

→ [Advanced Testing](TESTING_ADVANCED.md), *Three shapes that do not work*

### A peer test is skipped and I did not ask for that

A peer whose port or profile cannot be resolved is skipped, with the reason printed. That is deliberate: the same test files then work both on a bench that has the extra board and on one that does not.

→ [Advanced Testing](TESTING_ADVANCED.md), *The plugin takes care of peer boards*
