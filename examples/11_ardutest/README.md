# 11_ardutest

[日本語版 (Japanese)](README.ja.md)

This example demonstrates the experimental `arduino_test` fixture with the ArduTest Arduino library.

ArduTest is an Arduino-side library. The sketch declares it in `sketch.yaml` through `libraries`, with a pinned version so the Arduino-side protocol implementation and the pytest-side fixture stay compatible.

This directory keeps the examples intentionally small:

- `ardutest_basic`: minimal `TEST_CASE` usage with `arduino_test.run()`
- `ardutest_metadata`: a compact example of requirements, config, logs, metrics, and a text artifact

For detailed protocol/API coverage and artifact-saving integration tests, see the ArduTest test suite:

https://github.com/tanakamasayuki/ArduTest/tree/main/tests

The example uses host execution by default:

```bash
uv run pytest examples/11_ardutest --profile=host
```

Run with a real board profile when hardware is available:

```bash
uv run --env-file .env pytest examples/11_ardutest --profile=uno
uv run --env-file .env pytest examples/11_ardutest --profile=esp32
```
