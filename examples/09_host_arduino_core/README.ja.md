# 09_host_arduino_core

このサンプルは、host machine 上で Arduino sketch をビルド・実行する board core を使う想定のサンプルです。

対象 board core:

- package index: `https://tanakamasayuki.github.io/host-arduino-core/package_index.json`
- FQBN: `lang-ship:host:host`

`arduino-cli compile` はローカルの gcc などを使って host 用の実行ファイルをビルドします。
`arduino-cli upload` はその実行ファイルを host 上で起動します。

host 実行ファイルは TCP/IP 接続用の port を出力または情報ファイルへ保存します。
plugin 側では、`--port=socket://localhost` のように port 番号なしの socket URL が指定された場合に、build 出力ディレクトリの `*.host-arduino.json` から `port` を読み取り、実際の接続先へ補完する方針です。

```json
{
  "pid": 21228,
  "port": 56789
}
```

想定コマンド:

```bash
uv run pytest examples/09_host_arduino_core --profile host --port=socket://localhost
```

port 番号が分かっている場合は、明示して実行できます。

```bash
uv run pytest examples/09_host_arduino_core --profile host --port=socket://localhost:56789
```

この場合、plugin は port 番号の補完を行わず、その socket URL をそのまま使います。
