# 10_build_flags

This sample demonstrates value-less compile-time defines through `[flags]` in `build_config.toml`.

```toml
[flags]
PYTEST_BUILD = true
ENABLE_TEST_HOOKS = true
DISABLED_FLAG = false
```

Only `true` entries are passed to `arduino-cli compile` as `-D<macro name>`.
`false` entries are not passed.

Expected command:

```bash
uv run pytest examples/10_build_flags
```

This sample checks in the sketch that `PYTEST_BUILD` and `ENABLE_TEST_HOOKS` are defined, then verifies the serial output from pytest.

The plugin does not add flags such as `PYTEST_BUILD` automatically.
Projects opt in by declaring the flags explicitly in `build_config.toml` when they need test-only hooks.

Keep these flags small and deliberate.
If a test flag switches to a substantially different code path, the test may no longer represent production behavior.
