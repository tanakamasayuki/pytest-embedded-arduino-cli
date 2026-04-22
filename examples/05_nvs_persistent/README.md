# 05_nvs_persistent

This sample demonstrates that ESP32 persistent storage is not erased by default.

- The default profile is `esp32`
- Use `--profile` explicitly if you add another ESP32-class target later
- This sample is specifically about ESP32 `Preferences` backed by NVS
- Unsupported profiles such as `uno` are not listed in `sketch.yaml` and are skipped before build if selected

On `uno`, the behavior is different and EEPROM would be a closer topic, but this sample is specifically about ESP32 `Preferences` backed by NVS.

Example:

```bash
uv run pytest -s examples/05_nvs_persistent --port=/dev/ttyUSB0
```

This sketch stores a boot counter in `Preferences`.
On ESP32, rerunning the test without erase will usually increase the stored value across runs.

The test only verifies that `BOOT_COUNT <n>` is reported.
To observe persistence, run the same command more than once and compare the printed value.

The same consideration applies to SPIFFS-like persistent storage.
Right after the first flash or after erase, the device may boot with an unformatted filesystem.
Formatting during mount can take noticeable time, so avoiding full erase on every run can be a practical choice.

In that case, design the test so it does not leave unwanted state behind.
For example, remove files created by the test at the beginning or end of the run to avoid side effects and storage exhaustion.

The actual sketch lives under `nvs_persistent/`.
