# 10_build_flags

このサンプルは、`build_config.toml` の `[flags]` で値なし compile-time define を渡す方法を示します。

```toml
[flags]
PYTEST_BUILD = true
ENABLE_TEST_HOOKS = true
DISABLED_FLAG = false
```

`true` の項目だけが `-D<macro名>` として `arduino-cli compile` に渡されます。
`false` の項目は渡されません。

想定コマンド:

```bash
uv run pytest examples/10_build_flags --port=socket://localhost
```

このサンプルでは `PYTEST_BUILD` と `ENABLE_TEST_HOOKS` が定義されていることを sketch 側で確認し、serial 出力を pytest から検証します。

`PYTEST_BUILD` のような flag は、plugin が自動では付与しません。
テスト時だけ有効にしたい hook がある場合に、project 側が明示的に `build_config.toml` へ書くための仕組みです。

ただし、テスト用 flag で本番と大きく異なる code path を作ると、本番の動作を確認できなくなることがあります。
この仕組みは、テスト用の小さな hook やログを有効にする程度に使うのが安全です。
