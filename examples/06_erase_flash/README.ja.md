# 06_erase_flash

このサンプルは、`EraseFlash=all` によって ESP32 の upload 挙動がどう変わるかを示します。

- デフォルト profile は `esp32` です
- このサンプルの `esp32` profile には `EraseFlash=all` を設定しています
- このサンプルは ESP32 の flash erase 挙動を対象にしています
- `uno` のような非対応 profile は `sketch.yaml` に含めておらず、指定した場合は build 前に skip されます

この例は `05_nvs_persistent` と対になるものです。
どちらも ESP32 の `Preferences` に起動回数を保存しますが、こちらは upload 前に flash 全体を消去するため、保存値が毎回リセットされます。

実行例:

```bash
uv run pytest -s examples/06_erase_flash --port /dev/ttyUSB0
```

erase が正しく行われていれば、毎回 `BOOT_COUNT 1` が出力されます。

実際の sketch は `nvs_erase_flash/` 配下にあります。
