# 11_ardutest

この例では、ArduTest Arduino ライブラリと experimental な `arduino_test` fixture の使い方を示します。

ArduTest は Arduino 側ライブラリです。sketch は `sketch.yaml` の `libraries` で ArduTest を宣言し、Arduino 側 protocol 実装と pytest 側 fixture の互換性を保つために version を固定します。

このディレクトリでは、目的ごとに sketch を分けています。

- `ardutest_basic`
  - 最小の `TEST_CASE` と `arduino_test.run()` の例
- `ardutest_metadata`
  - requirement metadata、required config、log、metric、text artifact の例

default は host 実行です。

```bash
uv run pytest examples/11_ardutest --profile=host
```

実機がある場合は board profile を指定して実行できます。

```bash
uv run --env-file .env pytest examples/11_ardutest --profile=uno
uv run --env-file .env pytest examples/11_ardutest --profile=esp32
```
