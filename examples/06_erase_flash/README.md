# 06_erase_flash

This sample demonstrates how `EraseFlash=all` changes ESP32 upload behavior.

- The default profile is `esp32`
- The `esp32` profile in this sample uses `EraseFlash=all`
- This sample focuses on ESP32 flash erase behavior
- Unsupported profiles such as `uno` are not listed in `sketch.yaml` and are skipped before build if selected

This example is paired with `05_nvs_persistent`.
Both sketches store a boot counter in ESP32 `Preferences`, but this sample erases flash before upload so the stored value is reset on each run.

Example:

```bash
uv run pytest -s examples/06_erase_flash --port /dev/ttyUSB0
```

The sketch should report `BOOT_COUNT 1` on every run as long as erase completes before upload.

The actual sketch lives under `nvs_erase_flash/`.
