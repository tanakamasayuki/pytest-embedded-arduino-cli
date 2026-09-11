# examples

[English](README.md)

`examples/` は、この plugin の機能を目的別に確認するための実行可能な参照実装です。初めて自分のprojectへ導入する場合は、先に [最初のテスト](../FIRST_TEST.ja.md) を使ってください。

番号は難易度を厳密に表すものではありません。`01` から全部を順番に実行する教材ではなく、必要な機能のサンプルを選んで読むための索引です。

## どこから始めるか

### 実機がある

まず `01_basic` で compile、upload、serial の往復を確認します。

```bash
uv run pytest examples/01_basic --profile=uno --port=/dev/ttyACM0
uv run pytest examples/01_basic --profile=esp32 --port=/dev/ttyUSB0
```

次に、pytest から値を送る `03_dut_input` を試すと、通常のテストの形が分かります。

### 実機がない

`09_host_arduino_core` から始めます。host core と C++ toolchain は必要ですが、serial device は使いません。

```bash
uv run pytest examples/09_host_arduino_core --profile=host
```

host core はロジックとserial protocolの確認用です。周辺機器、割り込み、実時間のタイミング、Flash/NVS、board固有APIは実機で確認してください。

### 実際のプロジェクト構成を見たい

`07_arduino_library_project` と `08_arduino_ide_project` は、ほかのサンプルとは独立したworkspaceです。それぞれの `tests/` へ移動して実行します。

## 目的別の一覧

| example | 必要なもの | 主題 | 関連する文書 |
| --- | --- | --- | --- |
| [`01_basic`](01_basic/README.ja.md) | 実機1台 | 最小のcompile・upload・serial往復 | [最初のテスト](../FIRST_TEST.ja.md) |
| [`02_env_define`](02_env_define/README.ja.md) | ESP32、Wi-Fi設定 | 環境変数をcompile-time defineへ渡す | [応用: 設定の優先順位](../TESTING_ADVANCED.ja.md#設定の優先順位と-env) |
| [`03_dut_input`](03_dut_input/README.ja.md) | 実機1台 | `dut.write()`による実行時入力 | [基本: 仕組み](../TESTING_BASICS.ja.md#どういう仕組みで動くか) |
| [`04_unity_basic`](04_unity_basic/README.ja.md) | ESP32 | device側アサーション | [基本: 合否の判定場所](../TESTING_BASICS.ja.md#合否を判定する場所は-2-つある) |
| [`05_nvs_persistent`](05_nvs_persistent/README.ja.md) | ESP32 | upload後も残るNVS | [基本: session、module、test](../TESTING_BASICS.ja.md#sessionmoduletest) |
| [`06_erase_flash`](06_erase_flash/README.ja.md) | ESP32 | upload前のFlash全消去 | [基本: session、module、test](../TESTING_BASICS.ja.md#sessionmoduletest) |
| [`07_arduino_library_project`](07_arduino_library_project/README.ja.md) | 実機1台 | Arduinoライブラリ用workspace | [基本: ディレクトリ構成](../TESTING_BASICS.ja.md#ディレクトリ構成) |
| [`08_arduino_ide_project`](08_arduino_ide_project/README.ja.md) | 実機1台 | Arduino IDE project用workspace | [基本: ディレクトリ構成](../TESTING_BASICS.ja.md#ディレクトリ構成) |
| [`09_host_arduino_core`](09_host_arduino_core/README.ja.md) | host core、C++ toolchain | ボードなしのsketch実行 | [基本: 0台](../TESTING_BASICS.ja.md#0-台-host-core-で動かす) |
| [`10_build_flags`](10_build_flags/README.ja.md) | host core、C++ toolchain | 値なしcompile-time flag | [応用: compile時のdefine](../TESTING_ADVANCED.ja.md#compile-時の-define) |
| [`11_ardutest`](11_ardutest/README.ja.md) | host coreまたは実機 | ArduTest fixture | [README: ArduTest](../README.ja.md#ardutest-fixture) |
| [`12_peer_host_core`](12_peer_host_core/README.ja.md) | host core、C++ toolchain | primaryとpeerの構成 | [基本: 2台](../TESTING_BASICS.ja.md#2-台-相手がいるテスト) |

`05` と `06`、`02` と `03` はそれぞれ対です。永続領域を残す/消す、値をcompile時/実行時に渡す、という違いを比較できます。

## 共通前提

- `arduino-cli` が `PATH` にあること
- 選択するprofileのplatformとversionを `sketch.yaml` で宣言し、Arduino CLIのindexから解決できること。versionは必ず指定し、環境へ事前導入されたcoreには依存しない
- 実機exampleではhostからアクセスできるserial portがあること

versionが見つからない場合はindexを更新します。

```bash
arduino-cli core update-index
arduino-cli lib update-index
```

追加のBoard Manager URLが必要なcoreでは、profileに `platform_index_url` を指定します。binaryを配布するprojectは製品のbuild versionに固定し、sourceを配布するprojectはテストしながら新しいcore versionへ追従するのが基本方針です。

リポジトリrootで引数なしの `uv run pytest` を実行すると、plugin自身のテストだけが走ります。exampleは必ずpathを指定してください。

## profileとport

primary profileは `--profile`、`default_profile`、profileが1つだけの場合の自動選択、の順で解決されます。複数profileが残ればエラーです。exampleでは使用するboardを明確にするため `--profile` の明示を勧めます。

portは `--flash-port`、`--port`、`TEST_SERIAL_PORT_<PROFILE>`、`TEST_SERIAL_PORT`、`sketch.yaml` の `socket://...` の順です。物理portは `--port=/dev/ttyUSB0` のように `=` 付きで書くとpytestのpath解釈との曖昧さを避けられます。繰り返し使う値は `.env` に置けます。

```bash
uv run --env-file .env pytest examples/01_basic --profile=esp32
```

## 実行方法

基本は1つずつ実行します。device logをconsoleでも見るなら `-s`、pluginが組み立てたコマンドは `-v`、解決したpath・profile・portまで見るなら `-vv` を付けます。

`--run-mode` は処理範囲を選びます。

- `all`: compile、upload、test。既定値
- `build`: compileのみ。pytestのtest itemはskipとして表示される
- `test`: 既存buildを使ってupload、test。先に同じprofileをbuildしておく必要がある

異なる機材や環境変数を要求するexampleが混在するため、`examples/` 全体の実行は通常の導入手順にはしていません。対応profileをまとめてcompileする場合は対象を明示します。

```bash
uv run pytest examples/01_basic examples/03_dut_input --profile=uno --run-mode=build
```

## exampleを保守するとき

- 主題を1つに絞る
- 起動時に一度だけ出す文字列より、pytestから問い合わせ可能なhandshakeを優先する
- 実行コマンド、必要なboard/core、期待する結果を各READMEに書く
- 新機能を追加したら、この表と対応するガイド節を相互リンクする
- 同じディレクトリの `.ino` は1つにし、補助コードは `.h` / `.cpp` にする
