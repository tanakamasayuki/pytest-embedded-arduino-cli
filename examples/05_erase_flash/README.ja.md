# 05_erase_flash

このサンプルは、`EraseFlash=all` によって ESP32 の upload 挙動がどう変わるかを示します。

- デフォルト profile は `esp32` です
- このサンプルの `esp32` profile には `EraseFlash=all` を設定しています
- `uno` はこの例では skip 用の経路としてだけ含めています

この例は `04_nvs_persistent` と対になるものです。
どちらも ESP32 の `Preferences` に起動回数を保存しますが、こちらは upload 前に flash 全体を消去するため、保存値が毎回リセットされます。

実行例:

```bash
uv run pytest -s examples/05_erase_flash --port /dev/ttyUSB0
```

erase が正しく行われていれば、毎回 `BOOT_COUNT 1` が出力されます。

実際の sketch は `nvs_erase_flash/` 配下にあります。
