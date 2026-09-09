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

## Reference

- **[ArduTest](https://github.com/tanakamasayuki/ArduTest)** — a library for deciding pass or fail on the device, used through the `arduino_test` fixture. It is one way to put the judgement on the device and you do not need it: Unity works, and so does simply printing the result from the sketch and checking it on the host. Convenient when it fits, nothing more.
- **[host-arduino-core](https://github.com/tanakamasayuki/host-arduino-core)** — what the guides call a **host core**. It builds a sketch as a PC program and is reached over a TCP socket instead of a serial port. Use it to check logic without hardware, and to run in CI. Its `tests/conftest.py` also shows a session-scoped autouse fixture that prepares the platform.
