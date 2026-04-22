# examples

`examples/` は、この plugin の使い方を確認するためのサンプル集です。

`uv run pytest` は `pyproject.toml` の `testpaths = ["tests"]` に従ってライブラリ自身のテストだけを実行します。
そのため、`examples/` 配下のサンプルは明示的に対象を指定して実行します。

## 共通前提

これらのサンプルは、実際のデバイスが利用できることを前提にしています。

- ベースラインとして確認している target は `esp32:esp32:esp32` です
- target を切り替えるときは `--profile` を明示して使います
- `--profile` を省略したい場合は、そのサンプルの `sketch.yaml` に `default_profile` を定義する前提です
- profile が 1 つだけのときの自動選択もサポートされますが、通常のサンプルではそれに依存しない方針です

共通の実行例:

```bash
uv run pytest examples/01_basic --port /dev/ttyUSB0
```

他の profile を使う例:

```bash
uv run pytest examples/01_basic --profile uno --port /dev/ttyACM0
```

個別の前提条件や補足は、各サンプルの `README.ja.md` に記載しています。

## Profile Selection

plugin の profile 解決順は次のとおりです。

1. `--profile`
2. `sketch.yaml` の `default_profile`
3. profile が 1 つだけのときの自動選択
4. profile が複数あり `default_profile` もない場合はエラー

このリポジトリの examples では、次の運用方針で揃えています。

- コマンド例では `--profile` の明示を優先する
- `--profile` なしで動かしたいサンプルは `default_profile` を定義する
- profile が 1 つだけであることにだけ依存する構成は避ける

## 実行方針

基本はサンプルごとに個別実行します。

実行中のデバイスログを直接見たい場合は `-s` を付けてください。
特に、実行ごとの差分をシリアル出力で確認したいサンプルでは有効です。

必要なら `examples/` 配下をまとめて実行できます。

```bash
uv run pytest examples/
```

## 基本機能

`--run-mode` はどこまで実行するかを制御します。

- `--run-mode=all`
  - compile、upload、test をまとめて実行する
- `--run-mode=build`
  - compile だけを実行する
- `--run-mode=test`
  - compile を省略し、既存の build 出力を再利用して upload と test を行う

serial port は次の優先順位で解決されます。

1. `--flash-port`
2. `--port`
3. `TEST_SERIAL_PORT_<PROFILE>`
4. `TEST_SERIAL_PORT`

plugin が何をしているか確認したい場合は verbosity を使います。

- `-v`
  - `arduino-cli compile` と `arduino-cli upload` の実行コマンドを表示する
- `-vv`
  - 上記に加えて `sketch_dir`、`build_path`、`profile`、`port` などの解決結果も表示する

サンプルは確認してほしい順に番号付きで並べています。

- `01_basic`
  - 最小構成の hello world
  - `esp32` をデフォルト profile として確認する最初のサンプル
  - `TEST_SERIAL_PORT` と `TEST_SERIAL_PORT_<PROFILE>` による port 解決もここで扱います
- `02_env_define`
  - 環境変数から compile-time define を渡す例
  - ESP32 系 target 向けの例で、Wi-Fi を題材に `build_config.toml` を説明します
- `03_dut_input`
  - `dut.write(...)` で serial 経由の実行時入力を渡す例
  - `esp32` と `uno` の両方で動きます
- `04_unity_basic`
  - ESP32 向けの最小 Unity テスト sketch
  - シリアル文字列の自前判定ではなく、デバイス側アサーションを使う例です
- `05_nvs_persistent`
  - ESP32 の `Preferences` / NVS が default では実行をまたいで残る例
  - ESP32 固有の永続領域を扱うため、非対応 profile は build 前に skip されます
- `06_erase_flash`
  - `EraseFlash=all` により ESP32 の永続データを upload 前に消去する例
  - `05_nvs_persistent` と対にして違いを見ます
- `07_arduino_library_project`
  - `tests/` を `uv` ルートにした実プロジェクト向けの Arduino ライブラリ構成
  - shell / batch の補助スクリプトを含む実用的なテストワークスペース例です

## ディレクトリ構成

各サンプルディレクトリは 1 つのテストアプリです。

```text
examples/
  01_basic/
    README.ja.md
    basic/
      sketch.yaml
      basic.ino
      test_basic.py
  02_env_define/
    README.ja.md
    wifi_env_define/
      sketch.yaml
      wifi_env_define.ino
      build_config.toml
      test_env_define.py
  03_dut_input/
    README.ja.md
    serial_dut_input/
      sketch.yaml
      serial_dut_input.ino
      test_dut_input.py
  04_unity_basic/
    README.ja.md
    unity_basic/
      sketch.yaml
      unity_basic.ino
      test_unity_basic.py
  05_nvs_persistent/
    README.ja.md
    nvs_persistent/
      sketch.yaml
      nvs_persistent.ino
      test_nvs_persistent.py
  06_erase_flash/
    README.ja.md
    nvs_erase_flash/
      sketch.yaml
      nvs_erase_flash.ino
      test_nvs_erase_flash.py
  07_arduino_library_project/
    README.ja.md
    demo_add_library/
      library.properties
      src/
      tests/
```

この plugin は、実行したテストファイルがあるディレクトリを sketch ディレクトリとして扱います。

## 補足

- `examples/pytest.ini` は `pytest-embedded` 由来の warning を抑制するためのローカル設定です
- `02_env_define` は `TEST_WIFI_SSID` と `TEST_WIFI_PASSWORD` の設定が必要です
- 実行中に `BOOT_COUNT` などのシリアル出力を見たい場合は `-s` が便利です
