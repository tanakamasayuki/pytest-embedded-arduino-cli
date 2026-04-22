# demo_add_sketch

This is a practical project example based on a sketch that can still be opened directly in Arduino IDE.

Project root:

- `basic_add/`
- `tests/`
- `.gitignore`

Test root:

- `tests/pyproject.toml`
- `tests/pytest.ini`
- `tests/.env.example`
- `tests/run_wsl.sh`

`tests/pyproject.toml` defines the `uv` workspace used for this test setup.
This example also adds `pytest-html` as a regular dependency.
The tests can run without it, but it is useful in practice because it produces an HTML report as `report.html`.

`tests/pytest.ini` contains that HTML report configuration.
It also ignores a warning from `pytest-embedded` that is usually not meaningful in day-to-day use.

The project-root `.gitignore` follows the same policy as this repository's top-level ignore list.
It ignores Python and `uv` local files, the HTML report, and common caches, and adds `tests/**/build/` for per-runner Arduino CLI build output in this layout.

Run commands from `tests/`.

Example:

```bash
cd examples/08_arduino_ide_project/demo_add_sketch/tests
cp .env.example .env
uv run --env-file .env pytest unity_wrapper_runner --profile esp32 --port=/dev/ttyUSB0
```

The `unity_wrapper_runner` sketch is the smallest example that runs Unity tests against the sketch-side code.

In this layout, the application must remain a regular sketch project for Arduino IDE.
That means the target code is not split out like a library project.
Instead, the runner keeps thin wrapper files that `#include` the real files under `../../basic_add/`.

Those wrappers are explicit static files.
They do not copy or generate source code at runtime.

## run_wsl.sh

`run_wsl.sh` is an example script for building in WSL while performing upload and test on the Windows side.

- Build can be noticeably faster in WSL than in a native Windows environment
- Serial port handling is often simpler on Windows, so this example keeps flashing and runtime interaction there

You can also access Windows-side serial devices from WSL by using USB/IP or a similar setup.
That is fine too, but when USB/IP is unavailable or undesirable, splitting build and upload this way is a practical option.

When building in WSL, a path managed inside the WSL filesystem can also be faster than a Windows-managed path.
This example assumes the source tree is handled from the WSL side for that reason.

The WSL-side `.venv` and the Windows-side `.venv` also cannot safely share the same path.
If you use `uv` from both sides, keep them in separate locations.

In this example, WSL keeps using `tests/.venv`, while Windows uses `UV_PROJECT_ENVIRONMENT_WIN` from `.env` to place a separate environment at `%TEMP%/.venv.pytest`.
That is why the Windows-side `.venv` path is configurable through `.env`.
