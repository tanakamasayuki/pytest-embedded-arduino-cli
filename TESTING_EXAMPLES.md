# Example Projects

[日本語](TESTING_EXAMPLES.ja.md)

Real, working projects that use what [Testing Basics](TESTING_BASICS.md) and [Advanced Testing](TESTING_ADVANCED.md) describe. Read what is under their `tests/` directory and you will find the items from those guides in use.

Sizes and layouts keep changing, so this page only says **what you can see** in each one.

## Read these first

- **[examples/](examples/)** — the minimal examples that ship in this repository. They are numbered and independent, so you can read them in order. They cover port resolution, passing compile-time defines from environment variables, NVS persistence and erasing, build flags, Unity, and the layouts for a library project and an Arduino IDE project. **The Unity example is here.**
- **[PCMFlowG722](https://github.com/tanakamasayuki/PCMFlowG722)** — the smallest shape among the real projects. It runs on a host core alone, so you can read and try it without owning a board. Its `tests/conftest.py` only deletes the `output/` files the sketch wrote.

## A clean example

- **[TinyGFX](https://github.com/tanakamasayuki/TinyGFX)** — a host core combined with ArduTest. `tests/` is split into per-feature directories, `tests/README` states the policy, and tests that need a person are kept in their own directory. An example of a layout that holds up as the suite grows.

## Several boards

- **[ESP32IRPulseKit](https://github.com/tanakamasayuki/ESP32IRPulseKit)** — the simplest of the multi-board projects. It verifies infrared sending and receiving across two boards and cross-checks the results against an existing library. It uses no `conftest.py` at all, only the standard features, and it shows plenty of `build_config.toml` usage.
- **[ESP32KeyBridge](https://github.com/tanakamasayuki/ESP32KeyBridge)** — a mid-sized multi-board setup. `tests/` is split into `unit/`, `peer/`, `manual/` and `single/`, with the policy written in `TEST_PLAN`. It has no `conftest.py` either.

## Tests a person operates

- **[PCMFlowUDP](https://github.com/tanakamasayuki/PCMFlowUDP)** — for audio, a person listening is the most reliable check. Those tests live in `manual/`, out of the default run.

## A large one

- **[EspUsbDevice](https://github.com/tanakamasayuki/EspUsbDevice)** — an example of a large setup, with two wiring styles side by side: two ESP32-S3 boards checked through a peer, and a single ESP32-P4 whose two USB controllers are joined by a cable, so the board tests itself. It reads as one library verified through two different arrangements. Its `tests/conftest.py` audits the serial logs and adds the findings to pytest's report.

## Unit tests with no core at all

Pure C++ that touches no Arduino API does not need a host core either. These tests call the compiler themselves and run the resulting binary. It is the fastest option available, and the trade-off is that nothing wraps the OS-dependent parts for you.

- **[EspBle / tests/unit](https://github.com/tanakamasayuki/EspBle/tree/main/tests/unit)** — a directory per subject, each holding a `.cpp` and the pytest file that builds and runs it. Codecs, parsers and lookup tables. Note the compiler flags: one of them pins the signedness of `char`, because the host and the target do not agree on it.
- **[EspUsbDevice / tests/unit/keymap](https://github.com/tanakamasayuki/EspUsbDevice/tree/main/tests/unit/keymap)** — the same shape with a twist worth reading. The logic under test lives in a source file that cannot be compiled on the host, so instead of copying it the test extracts the pieces it needs from the real sources at run time and compiles those. The assertions run against the production tables rather than a duplicate that could drift.

## Build tests in CI

The full example-by-profile matrix is orchestrated outside this plugin. Each job may use `--run-mode=build` or invoke `arduino-cli compile` directly. These are real workflows in the shapes [Advanced Testing](TESTING_ADVANCED.md) describes.

- **[EspUsbHost / build-check.yml](https://github.com/tanakamasayuki/EspUsbHost/blob/main/.github/workflows/build-check.yml)** — the every-push shape. A matrix runs one job per profile, each building all the examples, with fail-fast turned off and the platform cache keyed on the `sketch.yaml` files. An example that does not declare a profile is skipped for that target rather than failing it.
- **[EspUsbDevice / build-check.yml](https://github.com/tanakamasayuki/EspUsbDevice/blob/main/.github/workflows/build-check.yml)** — A production example combining a per-profile matrix, Arduino CLI caching, and an index refresh after cache restoration. A small Python script inspects each `sketch.yaml` and compiles only examples declaring the selected profile.
- **[EspUsbHost / version-matrix.yml](https://github.com/tanakamasayuki/EspUsbHost/blob/main/.github/workflows/version-matrix.yml)** — the on-demand sweep. Manual only, decomposed into one job per core version because several installs do not fit in one runner, then aggregated into a Markdown matrix that is committed to the repository. It records pass, fail or not-applicable per cell and exits successfully, so a red cell does not fail the job.
- **[EspBle / compile-examples.yml](https://github.com/tanakamasayuki/EspBle/blob/main/.github/workflows/compile-examples.yml)** — the simplest shape: one job walking every `sketch.yaml` under `examples/` and compiling each with its own profile. Start here when a matrix is more than you need.
- **[EspBle / board-matrix.yml](https://github.com/tanakamasayuki/EspBle/blob/main/.github/workflows/board-matrix.yml)** — every example against every target board for one core version, kept manual, writing a coverage document into the repository.

## Pure unit tests in CI

- **[EspBle / unit-tests.yml](https://github.com/tanakamasayuki/EspBle/blob/main/.github/workflows/unit-tests.yml)** — Uses neither a board nor an Arduino core. Pytest invokes the system `g++` to build and run pure C++ product code, keys the uv cache on `tests/uv.lock`, and runs with `tests/` as its working directory. It passes no serial port or `.env`.

## Host rendering and generated-site publishing in CI

- **[LGFXScreenBuilderScreenshotTest / screenshots.yml](https://github.com/tanakamasayuki/LGFXScreenBuilderScreenshotTest/blob/main/.github/workflows/screenshots.yml)** — Uses the host core's `mode=lgfx` and LovyanGFX's SDL2 backend to render every profile × scene headlessly to PNG. Pytest checks image and gallery completeness, commits `docs/` for [GitHub Pages](https://tanakamasayuki.github.io/LGFXScreenBuilderScreenshotTest/), and also retains it as an Actions artifact. This does not test a physical LCD or compare pixels to golden images; it automates completeness checks and presents the full gallery for visual review.

## Reference

- **[ArduTest](https://github.com/tanakamasayuki/ArduTest)** — a library for deciding pass or fail on the device, used through the `arduino_test` fixture. It is one way to put the judgement on the device and you do not need it: Unity works, and so does simply printing the result from the sketch and checking it on the host. Convenient when it fits, nothing more.
- **[host-arduino-core](https://github.com/tanakamasayuki/host-arduino-core)** — what the guides call a **host core**. It builds a sketch as a PC program and is reached over a TCP socket instead of a serial port. Use it to check logic without hardware, and to run in CI. Its `tests/conftest.py` also shows a session-scoped autouse fixture that prepares the platform.
