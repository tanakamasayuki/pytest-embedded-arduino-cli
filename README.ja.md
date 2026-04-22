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
uv run pytest tests/my_app --port=/dev/ttyACM0
```

`sketch.yaml` の profile を選ぶ例:

```bash
uv run pytest tests/my_app --profile esp32s3 --port=/dev/ttyACM0
```

build のみ:

```bash
uv run pytest tests/my_app --run-mode=build
```

既存 build artifact を使って upload してから test:

```bash
uv run pytest tests/my_app --run-mode=test --port=/dev/ttyACM0
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

`pytest` の引数解釈の都合で、`--port` や `--flash-port` のように path を受け取る option は、`--port=/dev/ttyUSB0` のように `=` 付きで書く方が安全です。
環境によっては `uv run pytest --port /dev/ttyUSB0` の形だと、その path を別の基準パスとして解釈してしまうことがあります。
必要なら `uv run pytest --rootdir . --port /dev/ttyUSB0` のように `--rootdir .` を明示しても構いません。

例:

```bash
export TEST_SERIAL_PORT_ESP32S3=/dev/ttyUSB1
uv run pytest tests/my_app --profile esp32s3
```

profile の解決順は次のとおりです。

1. `--profile` が指定されていればその profile を使う
2. そうでなければ、`sketch.yaml` に `default_profile` が定義されていればそれを使う
3. そうでなければ、`sketch.yaml` の profile が 1 つだけならそれを自動選択する
4. それ以外で profile が複数ある場合は、曖昧なためエラーになる

実運用では `--profile` を明示することを推奨します。
`--profile` を省略したい場合は、`sketch.yaml` に `default_profile` を定義してください。
profile が 1 つだけのときの自動選択は fallback としてサポートしていますが、通常の設定ではそれに依存しない方が明確です。

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
uv run pytest tests/my_app --port=/dev/ttyACM0
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

- `examples/01_basic`
  - 最小構成の hello world
  - `esp32` をデフォルト profile としつつ `uno` もサポートする
  - `TEST_SERIAL_PORT` と `TEST_SERIAL_PORT_<PROFILE>` による serial port 解決も含む
- `examples/02_env_define`
  - 環境変数から compile-time define を渡す例
  - ESP32 系 target 向けに、Wi-Fi を題材として `build_config.toml` を説明する
- `examples/03_dut_input`
  - `dut.write(...)` による serial 経由の実行時入力を示す
  - `esp32` と `uno` の両方で動く
- `examples/04_unity_basic`
  - ESP32 向けの最小 Unity テスト sketch を示す
- `examples/05_nvs_persistent`
  - ESP32 の `Preferences` / NVS が default では残ることを示す
  - ESP32 固有の永続領域を扱うため、非対応 profile は build 前に skip される
- `examples/06_erase_flash`
  - `EraseFlash=all` で ESP32 の永続データを upload 前に消去する例
  - `05_nvs_persistent` と対にして使う
- `examples/07_arduino_library_project`
  - `tests/` を `uv` ルートにした実プロジェクト向けの Arduino ライブラリ構成を示す
  - `run_wsl.sh` を含む実用的なテストワークスペース例
- `examples/08_arduino_ide_project`
  - `tests/` を `uv` ルートにした Arduino IDE 向け sketch プロジェクト構成を示す
  - ライブラリ分離できないコードを薄い wrapper `#include` で runner から参照する例

`examples/` 配下の実行方法は [examples/README.ja.md](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli/blob/main/examples/README.ja.md) にまとめています。

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
