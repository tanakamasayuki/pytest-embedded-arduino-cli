# 03_dut_input

このサンプルは、`dut` 経由で実行時にデバイスへ値を渡す方法を示します。

- デフォルト profile は `esp32` です
- `uno` を使う場合は `--profile` を明示します
- sketch は serial 入力を待つだけなので、同じ流れを両方の board で使えます

このサンプルは `default_profile: esp32` を定義しているため、`--profile` なしでも動きます。

これは `02_env_define` の代替例です。
たとえば機密情報のように firmware へ埋め込みたくない値を扱うときは、こちらの方法を使います。

実行例:

```bash
uv run pytest examples/03_dut_input --port=/dev/ttyUSB0
```

他の profile を使う例:

```bash
uv run pytest examples/03_dut_input --profile uno --port=/dev/ttyACM0
```

テストは `READY` を待ってから `dut.write(...)` で1行送り、デバイスからの応答を検証します。

実際の sketch は `serial_dut_input/` 配下にあります。
