# 07_arduino_library_project

This example shows a practical Arduino library project layout.

- The library source lives at the project root
- The test workspace lives under `tests/`
- `uv` is executed from `tests/`
- Build, upload, profile selection, and port resolution are handled by this plugin
- This example should be treated as an independent project example rather than another `examples/0x_*` sample with the same execution model
- `pyproject.toml` and `.env.example` live under `demo_add_library/tests/`, and the `uv` virtual environment is managed separately in that workspace

The structure is intentionally close to a practical Arduino library repository layout.

The sample project lives under `demo_add_library/`.
