# 08_arduino_ide_project

This example shows a project layout for a sketch that can still be opened directly in Arduino IDE.

- The application code stays in a regular Arduino sketch directory
- The test workspace lives under `tests/`
- `uv` is executed from `tests/`
- Build, upload, profile selection, and port resolution are handled by this plugin
- This example should be treated as an independent project example rather than another `examples/0x_*` sample with the same execution model
- `pyproject.toml` and `.env.example` live under `demo_add_sketch/tests/`, and the `uv` virtual environment is managed separately in that workspace

Because Arduino IDE compatibility is the priority here, the target code cannot be separated as cleanly as in `07_arduino_library_project`.
For that reason, the test runner keeps thin wrapper files that explicitly `#include` the real sketch-side `.h` / `.cpp` files.

The sample project lives under `demo_add_sketch/`.
