# pytest-embedded-arduino-cli

[English README](README.md)

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
