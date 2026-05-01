# 11_ardutest

This example demonstrates the experimental `arduino_test` fixture with the ArduTest Arduino library.

ArduTest is an Arduino-side library. The sketch declares it in `sketch.yaml` through `libraries`, with a pinned version so the Arduino-side protocol implementation and the pytest-side fixture stay compatible.

This directory is split into two sketches:

- `ardutest_basic`
  - Minimal `TEST_CASE` usage with `arduino_test.run()`
- `ardutest_metadata`
  - Requirement metadata, required config, logs, metrics, and text artifacts

The example uses host execution by default:

```bash
uv run pytest examples/11_ardutest --profile=host
```

Run with a real board profile when hardware is available:

```bash
uv run --env-file .env pytest examples/11_ardutest --profile=uno
uv run --env-file .env pytest examples/11_ardutest --profile=esp32
```
