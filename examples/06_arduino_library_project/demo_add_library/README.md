# demo_add_library

This is a small Arduino library project used as a realistic test layout example.

Project root:

- `library.properties`
- `src/`
- `tests/`

Test root:

- `tests/pyproject.toml`
- `tests/pytest.ini`
- `tests/.env.example`
- `tests/run.sh`, `tests/run.bat`, and related helper scripts

Run commands from `tests/`.

Example:

```bash
cd examples/06_arduino_library_project/demo_add_library/tests
cp .env.example .env
uv run --env-file .env pytest serial_runner --profile esp32
```

The `serial_runner` sketch uses the library directly.
The `unity_runner` sketch shows how to run ESP32 Unity-based tests in the same project layout.

Each runner keeps its own `sketch.yaml` next to the `.ino` file.
In this example, `sketch.yaml` points back to the library root with `libraries: - dir: ../../`.
