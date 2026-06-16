# 09_host_arduino_core

[English](README.md)

このサンプルは、host machine 上で Arduino sketch をビルド・実行する board core を使う想定のサンプルです。

対象 board core:

- package index: `https://tanakamasayuki.github.io/host-arduino-core/package_index.json`
- FQBN: `lang-ship:host:host`

`arduino-cli compile` はローカルの gcc などを使って host 用の実行ファイルをビルドします。
`arduino-cli upload` はその実行ファイルを host 上で起動します。

host 実行ファイルは TCP/IP 接続用の port を出力または情報ファイルへ保存します。
このサンプルの `sketch.yaml` には `port: socket://localhost` を設定しているため、pytest コマンドでは `--port` を省略できます。
plugin 側では、build 出力ディレクトリの `*.host-arduino.json` から runtime の `port` を読み取り、実際の接続先へ補完します。

```json
{
  "pid": 21228,
  "port": 56789
}
```

## 位置づけ

このサンプルは、純粋なロジックや serial protocol を実機なしで確認するための簡易テストです。
CI や開発中の早い確認には便利ですが、実機テストの代替ではありません。

host machine 上での実行結果は、OS、gcc などの toolchain version、host Arduino core が提供する `Serial` class などの platform 実装差に影響されます。
実機の peripheral、timing、割り込み、メモリ配置、Flash/NVS、board 固有 API の確認には使えません。

また、この profile で compile が通っても、本番で使う board core / board option で compile が通るとは限りません。
実運用では、本物の board profile を使った build test と実機テストを別途行ってください。

想定コマンド:

```bash
uv run pytest examples/09_host_arduino_core --profile host
```

port 番号が分かっている場合は、明示して実行できます。

```bash
uv run pytest examples/09_host_arduino_core --profile host --port=socket://localhost:56789
```

この場合、plugin は port 番号の補完を行わず、その socket URL をそのまま使います。
