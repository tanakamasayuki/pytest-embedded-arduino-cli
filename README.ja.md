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

`sketch.yaml` で platform や library の version を指定する場合、Arduino CLI はローカルの package index / library index からそれらを解決します。
毎回のテスト実行で index を更新する必要はありませんが、定期的に、または CI / release 確認の前に更新しておく運用を推奨します。
指定した platform や library の version が見つからず build に失敗する場合は、次のコマンドで index を更新してから再実行してください。

```bash
arduino-cli core update-index
arduino-cli lib update-index
```

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

Arduino CLI の clean compile を強制する例:

```bash
uv run pytest tests/my_app --clean
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
- `--peer-profile=NAME:PROFILE`
- `--peer-port=NAME:PORT`
- `--clean`
- `--save-state`
- `--save-state-dir=PATH`
- `--arduino-test-timeout=SECONDS`
- `--arduino-test-artifact-dir=PATH`
- `--arduino-test-missing-config=skip|error`

`--clean` は `arduino-cli compile` に `--clean` を渡します。
Arduino CLI の incremental build cache を使わずに再 build したいときに使います。
ArduTest の artifact 保存先 directory も、実行前に directory ごと削除します。

`--save-state` を指定すると、ローカル開発用にテストの検証状態を `state.json` に記録します。
既定値は無効です。
有効化すると、profile ごとにテスト結果が `.pytest-results/state.json` に記録されます（`--save-state-dir` で別の directory に変更可能）。
この機能は開発中にテストの pass/fail を追跡する際に便利で、外部の CI システムに依存しません。

使用例:

```bash
uv run pytest tests/my_app --profile esp32 --port=/dev/ttyACM0 --save-state
```

状態ファイルの構造 (`.pytest-results/state.json`):

```json
{
  "schema_version": 1,
  "updated_at": "2026-05-11T12:00:00.123456+09:00",
  "profiles": {
    "esp32": {
      "tests": {
        "tests/my_app/test_my_app.py::test_something": {
          "last_result": "passed",
          "last_run_at": "2026-05-11T12:00:00.123456+09:00",
          "last_success_at": "2026-05-11T12:00:00.123456+09:00"
        }
      }
    }
  }
}
```

peer test（複数 DUT）の場合、primary DUT の状態のみ記録されます。

`--save-state-dir` は `state.json` の保存先 directory を指定します。
既定値は `.pytest-results` です（pytest rootdir からの相対 path。絶対 path の場合はそのまま使用）。

`--arduino-test-artifact-dir` は ArduTest artifact の保存先 root を指定します。
既定値は `ardutest` で、pytest の `rootdir` からの相対 path として解決されます。
保存先 directory は artifact を保存する時点で自動生成され、artifact が発生しない実行では空 directory を作りません。

`--arduino-test-missing-config` は、ArduTest の必須 config が未指定だった場合の扱いを指定します。
既定値は `skip` です。未指定 config を pytest error にしたい場合は `error` を指定します。

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
5. `sketch.yaml` の `profiles.<PROFILE>.port`。ただし `socket://...` URL の場合のみ

`pytest` の引数解釈の都合で、`--port` や `--flash-port` のように path を受け取る option は、`--port=/dev/ttyUSB0` のように `=` 付きで書く方が安全です。
環境によっては `uv run pytest --port /dev/ttyUSB0` の形だと、その path を別の基準パスとして解釈してしまうことがあります。
必要なら `uv run pytest --rootdir . --port /dev/ttyUSB0` のように `--rootdir .` を明示しても構いません。

host 上で動く Arduino core など、TCP/IP 経由で DUT に接続する target では、`pytest-embedded-serial` / pyserial の URL 形式を使う方針です。
選択された `sketch.yaml` profile に `port: socket://localhost` が定義されている場合は、`--port=socket://localhost` を省略できます。

```bash
uv run pytest tests/my_app --profile host
```

`socket://localhost:56789` のように port 番号まで指定した場合は、その socket に直接接続します。
`socket://localhost` のように port 番号を省略した場合は、build 出力ディレクトリに生成される `*.host-arduino.json` から `port` を読み取り、`socket://localhost:<port>` として DUT に接続する想定です。
この解決では upload の標準出力ではなく、host-arduino の情報ファイルを優先して参照します。

```json
{
  "pid": 21228,
  "port": 56789
}
```

host 上の実行は、実機なしで純粋なロジックや serial protocol の簡易的な確認を行うための前段テストです。
実行結果は host machine の OS、gcc などの toolchain version、host Arduino core の `Serial` class 実装に影響されるため、実機上の動作を保証するものではありません。
実機依存の peripheral、timing、割り込み、メモリ配置、Flash/NVS、board 固有 API は実機で確認してください。
また、compile が通るかどうかも board core や platform ごとに差が出るため、本番で使う board profile での build test は別途実行することを推奨します。
`socket://...` port では、host Arduino core で 1 byte ずつ redirect されて極端に遅くなる挙動を避けるため、この plugin が serial read を chunk 化します。

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

## peer DUT

追加 DUT が必要なテストでは、primary sketch と同じディレクトリ直下に `peer_<name>/` sketch ディレクトリを置きます。
primary sketch は従来通り `dut` として扱われ、peer sketch は `peers` fixture から参照できます。

```text
tests/
  my_app/
    sketch.yaml
    my_app.ino
    test_my_app.py
    peer_echo/
      sketch.yaml
      peer_echo.ino
```

```python
def test_with_peer(dut, peers):
    echo = peers["echo"]

    dut.expect_exact("MAIN_READY")
    echo.expect_exact("ECHO_READY")
```

peer DUT は `peers` fixture を要求したテストでだけ準備されます。
`dut` だけを使うテストでは、`peer_*` ディレクトリは無視されます。
`peers` を要求すると、検出されたすべての peer DUT が有効化されます。
`peers["<name>"]` は、接続済み peer を参照するための mapping API です。

起動順は固定です。

1. primary DUT を先に build / upload する
2. peer DUT を peer 名順で build / upload する
3. peer DUT に接続し、`peers` から参照できるようにする
4. primary DUT に接続し、`dut` として参照できるようにする

実機 serial では、reset や upload 直後に sketch が短時間だけ出力する起動メッセージを Python 側が取りこぼす可能性があります。
host Arduino core の socket 実行では問題になりにくいですが、実機テストでは sketch 側で十分な待機、READY の再送、または Python 側からの入力を待つ handshake を用意することを推奨します。

peer 設定のために `sketch.yaml` は拡張しません。
各 peer ディレクトリは、`.ino` と `sketch.yaml` を持つ通常の sketch ディレクトリです。

peer profile は次の順で解決します。

1. `--peer-profile <name>:<profile>`
2. `peer_<name>/sketch.yaml` の `default_profile`
3. 解決できなければ peer テストを skip

`--profile` は primary DUT 専用で、peer DUT には継承されません。
peer DUT では profile が 1 つだけでも自動選択しません。
`--peer-profile` なしで動かしたい peer では、その peer の `sketch.yaml` に `default_profile` を定義してください。

peer port は次の順で解決します。

1. `--peer-port <name>:<port>`
2. `TEST_SERIAL_PORT_PEER_<NAME>_<PROFILE>`
3. `TEST_SERIAL_PORT_PEER_<NAME>`
4. peer 側 `sketch.yaml` の `profiles.<PROFILE>.port`。ただし `socket://...` URL の場合のみ
5. 解決できなければ peer テストを skip

`--peer-profile` と `--peer-port` は複数回指定できます。
カンマ区切りではなく、peer ごとに option を 1 回ずつ指定します。

```bash
uv run pytest tests/my_app \
  --profile esp32 \
  --peer-profile echo:host \
  --peer-port echo:socket://localhost
```

compile-time define を渡したい場合は、sketch ディレクトリに `build_config.toml` を置きます。

```toml
[defines]
TEST_WIFI_SSID = "WIFI_SSID"
TEST_WIFI_PASSWORD = "WIFI_PASSWORD"

[flags]
PYTEST_BUILD = true
ENABLE_TEST_HOOKS = true
```

`[defines]` の左側は環境変数名、右側は C/C++ 側で使う define 名です。
例えば `TEST_WIFI_SSID` は compile 時に `-DWIFI_SSID="..."` に変換されます。
`[flags]` は値なし define 用です。
`true` の項目だけが `-DPYTEST_BUILD` のように渡され、`false` の項目は渡されません。

実行前に対応する環境変数を設定しておくと、plugin が `arduino-cli compile --build-property build.extra_flags=...` に変換して渡します。

```bash
export TEST_WIFI_SSID=my-ssid
export TEST_WIFI_PASSWORD=my-password
uv run pytest tests/my_app --port=/dev/ttyACM0
```

これらの値は `uv run` の dotenv 読み込みでも渡せます。
`--env-file` は pytest ではなく `uv` の option なので、`pytest` より前に書きます。

```bash
uv run --env-file .env pytest tests/my_app --port=/dev/ttyACM0
```

環境変数が未設定でも、その define には空文字が渡されます。
未設定をどう扱うかは、テスト側または sketch 側で判断できます。
`PYTEST_BUILD` のようなテスト用 flag は plugin が自動では付与しません。
必要な project が `build_config.toml` の `[flags]` で明示してください。

これらの defines/flags は `arduino-cli compile --build-property <property>=...` で渡され、plugin が投入先プロパティを自動選択します。platform が空にしている host / AVR では `build.extra_flags`、ESP32 では `build.defines` を使います（ESP32 の `build.extra_flags` は platform が値を入れており、上書きするとビルドが壊れるため）。検出プローブを省いて約1秒速くしたい場合は、投入先を明示できます。

```toml
build_property = "build.defines"        # 全 profile 共通

[profiles.esp32]
build_property = "build.defines"        # profile 別の override
```

## verbosity とログ

コマンド表示には pytest 標準の verbosity を使います。

- `-v`
  - `arduino-cli compile` / `arduino-cli upload` の実行コマンドを表示
- `-vv`
  - 上記に加えて `cwd`、`sketch_dir`、`build_path`、`profile`、`port` なども表示

### シリアルログを最後まで残す

`dut.expect(...)` は pattern がマッチした時点で読み取りを終えるため、マッチした行の**後**にデバイスが送るバイトは `dut.log` に届く保証がなく、**行の途中で切れる**ことがあります。これはデバイス異常ではなく取り込みのタイミングの問題です。ログファイルとライブの `-s` コンソールは同じ流れから書かれており、close 時に流れ切らなかった末尾が落ちます。

plugin はシリアル close 時に受信バッファをベストエフォートでドレインするため、通常は `dut.log` が `-s` とほぼ同じところまで埋まります。ただし完全保証ではありません。末尾出力を確実に残したいときは:

- デバイスが最終行に終端マーカーを出し、それを `expect` する（読み取りが本当の終端まで伸びる）:

  ```python
  dut.expect_exact("=== END ===")
  ```

- もしくはテスト終了前に明示的にドレインする:

  ```python
  import pexpect

  dut.expect_exact("確認したい最後の行")
  dut.expect(pexpect.TIMEOUT, timeout=2)  # 残りを読み切る
  ```

なお `arduino_test.run()` は ArduTest の `RESULT` event で読み取りを止めるため、`RESULT` 後に出る `LOG` / tick 行は、あとからドレインしない限り収集されません。

## ArduTest fixture

この package には、別管理の Arduino 側 ArduTest ライブラリを使う sketch 向けの実験的な `arduino_test` fixture も含まれます。
ArduTest は sketch の `sketch.yaml` で宣言し、再現性のあるテストにするために library version もそこで固定する想定です。
細かい使い方は API と protocol が固まってから `examples/` に追加します。

```python
def test_board(arduino_test):
    arduino_test.run()
```

ArduTest 側が failed または error の結果を返した場合、`arduino_test.run()` が pytest の失敗として扱います。
収集した log、metric、artifact、metadata まで確認したい場合だけ、追加の assert を書きます。

現在の fixture は ArduTest protocol version `1` を使います。

固定値や test-local な ArduTest の値は fixture method で渡します。

```python
def test_sample_rate(arduino_test):
    arduino_test.set_capability("measurement.current")
    arduino_test.set_config("sample_rate", 1000)
    arduino_test.run("test_sample_rate")
```

実行する PC、接続先、実機環境、secret に依存する値は、環境変数、`.env`、CI variables で渡します。

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
- `examples/09_host_arduino_core`
  - host machine 上で Arduino sketch をビルド・実行する board core の利用例
  - `sketch.yaml` の `port: socket://localhost` で、host 実行ファイルの TCP/IP 接続先へ接続する想定
  - 純粋なロジックや serial protocol の簡易確認向けで、実機テストや実 board profile の build test の代替ではない
- `examples/10_build_flags`
  - `build_config.toml` の `[flags]` で値なし compile-time define を渡す例
  - `PYTEST_BUILD` のようなテスト用 flag を project 側が明示する方法を示す
- `examples/11_ardutest`
  - ArduTest Arduino ライブラリと experimental な `arduino_test` fixture の最小例
  - protocol / API や artifact 保存の詳しい test は ArduTest 側の test suite を参照: https://github.com/tanakamasayuki/ArduTest/tree/main/tests

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
- host Arduino core の TCP/IP 接続補助
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
