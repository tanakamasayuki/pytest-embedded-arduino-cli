# pytest-embedded-arduino-cli

[English README](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli/blob/main/README.md)

`pytest-embedded` と `arduino-cli` を使って Arduino プロジェクトをテストするための pytest plugin です。

## 概要

`pytest-embedded-arduino-cli` は、`pytest-embedded` の汎用的な DUT / serial / expect の流れを活かしつつ、Arduino 向けの build / upload を `arduino-cli` に置き換える小さな plugin です。

このパッケージは `pytest-embedded-arduino` には依存しません。ESP32 固有の前提に寄せず、より広い Arduino プロジェクトで使いやすい構成を目指しています。

## 設計方針

- build は `arduino-cli compile`
- upload は `arduino-cli upload`
- test runtime は `pytest-embedded` を土台にする
- `EspSerial` や ESP 固有の flashing service は使わない
- sketch 設定は `sketch.yaml` と `--profile` から解決する
- テストファイルのあるディレクトリを sketch ディレクトリとして扱う

## セットアップ

```bash
uv init
uv add pytest-embedded-arduino-cli
uv sync
```

通常依存として次を含みます。

- `pytest`
- `pytest-embedded`
- `pytest-embedded-serial`
- `PyYAML`

## 前提条件

- `arduino-cli` が `PATH` に入っていること
- 必要な Arduino board core がインストール済みであること
- 実機テスト時にホストからアクセスできる serial port があること

## 想定レイアウト

基本は 1 つのテストアプリごとに 1 つの sketch ディレクトリを想定します。

```text
tests/
  my_app/
    sketch.yaml
    my_app.ino
    test_my_app.py
```

pytest が特定の `.py` を実行したとき、この plugin はそのファイルがあるディレクトリを sketch ディレクトリとして扱います。build 設定は最も近い `sketch.yaml` から解決します。

## 使い方

build・upload・test をまとめて実行する例:

```bash
uv run pytest tests/my_app --port /dev/ttyACM0
```

`sketch.yaml` の profile を選ぶ例:

```bash
uv run pytest tests/my_app --profile esp32s3 --port /dev/ttyACM0
```

build のみ:

```bash
uv run pytest tests/my_app --run-mode=build
```

既存 build artifact を使って upload してから test:

```bash
uv run pytest tests/my_app --run-mode=test --port /dev/ttyACM0
```

`--run-mode=test` は compile を行わず、既存 build 出力を使って upload してから test を実行します。

このパッケージ自身のテストを実行する例:

```bash
uv run pytest
```

## 主な option

- `--run-mode=all|build|test`
- `--profile`

実行時の制御には `pytest-embedded` 標準 option を使います。主なものは次です。

- `--port`
- `--flash-port`
- `--baud`
- `--embedded-services`

`pytest-embedded-serial` は通常依存に含めているため、実機テストで serial service を追加インストールなしで使えます。
`--embedded-services` を指定しない場合、この plugin は `serial` をデフォルトで有効化します。

profile ごとの serial port は次の順で解決します。

1. `--flash-port`
2. `--port`
3. `TEST_SERIAL_PORT_<PROFILE>`
4. `TEST_SERIAL_PORT`

例:

```bash
export TEST_SERIAL_PORT_ESP32S3=/dev/ttyUSB1
uv run pytest tests/my_app --profile esp32s3
```

`--profile` を省略した場合でも、plugin は `sketch.yaml` から解決した profile を使います。`default_profile` もこの対象です。

compile-time define を渡したい場合は、sketch ディレクトリに `build_config.toml` を置きます。

```toml
[defines]
TEST_WIFI_SSID = "WIFI_SSID"
TEST_WIFI_PASSWORD = "WIFI_PASSWORD"
```

左側は環境変数名、右側は C/C++ 側で使う define 名です。
例えば `TEST_WIFI_SSID` は compile 時に `-DWIFI_SSID="..."` に変換されます。

実行前に対応する環境変数を設定しておくと、plugin が `arduino-cli compile --build-property build.extra_flags=...` に変換して渡します。

```bash
export TEST_WIFI_SSID=my-ssid
export TEST_WIFI_PASSWORD=my-password
uv run pytest tests/my_app
```

環境変数が未設定でも、その define には空文字が渡されます。
未設定をどう扱うかは、テスト側または sketch 側で判断できます。

## verbosity とログ

コマンド表示には pytest 標準の verbosity を使います。

- `-v`
  - `arduino-cli compile` / `arduino-cli upload` の実行コマンドを表示
- `-vv`
  - 上記に加えて `cwd`、`sketch_dir`、`build_path`、`profile`、`port` なども表示

## 例

```python
def test_hello(dut):
    dut.expect_exact("hello from arduino")
```

```cpp
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("hello from arduino");
}

void loop() {}
```

追加サンプル:

- `examples/wifi`
  - ESP32 / ESP32-S3 で Wi-Fi 接続を行う
  - Wi-Fi 非対応 profile の例として `uno` では skip する
  - `TEST_WIFI_SSID` と `TEST_WIFI_PASSWORD` を使う
  - ボードが `WIFI_OK <ip-address>` を出力することを検証する

## warning について

`PytestExperimentalApiWarning: record_xml_attribute is an experimental feature` が出ることがあります。

これはこの plugin ではなく `pytest-embedded` 由来の warning です。通常は無視して構いません。
気になる場合は `pytest.ini`、`pyproject.toml`、または `examples/pytest.ini` のようなローカル設定で warning filter を追加して抑制してください。

## この plugin が目指していないもの

- `pytest-embedded-arduino` の drop-in replacement
- ESP 固有の flashing layer
- board 自動検出ツール

## 今後の拡張候補

- board family ごとの upload strategy
- artifact 探索の改善
- serial reset / monitor helper
- 複数デバイス対応
- `fqbn` や sketch path の override

## リリース方法

このリポジトリは GitHub Actions ベースでリリースします。

リリース前に最低限やること:

- `CHANGELOG.md` の `## Unreleased` を更新する
- 必要ならローカルで `uv run pytest tests` を通しておく

リリース手順:

1. GitHub Actions を開く
2. `Release` workflow を手動実行する
3. `0.1.0` のような version を入力する
4. PyPI に publish するかを選ぶ

workflow が行うこと:

- `pyproject.toml` と `src/pytest_embedded_arduino_cli/__init__.py` の version 更新
- `CHANGELOG.md` の `## Unreleased` を `## <version>` に反映
- テストとパッケージ build の実行
- release 用 commit と `v<version>` tag の作成
- GitHub Release の作成
- 必要に応じて PyPI への publish

PyPI publish は GitHub Actions の Trusted Publishing を前提にしています。
