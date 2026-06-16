# pytest-embedded-arduino-cli 仕様書

[English](SPEC.md)

## 1. 文書の目的

本書は、新規 Python パッケージ / pytest plugin `pytest-embedded-arduino-cli` の要件を整理するための仕様書である。

本プラグインは `pytest-embedded` の core / serial / expect を土台にしつつ、Arduino 向けの build / upload を `arduino-cli` ベースで提供することを目的とする。

既存の `pytest-embedded-arduino` 互換を主目的にはせず、ESP 固有実装から距離を取り、将来的に ESP32 以外の Arduino 対応ボードへ広げやすい構成を優先する。

## 2. 背景

- 既存の `pytest-embedded` は DUT・serial・expect などのコア機能を汎用的に再利用できる。
- 一方で `pytest-embedded-arduino` は Arduino 向けであっても ESP 系実装に寄っている。
- 特に serial 周りが `EspSerial` ベースで構成されているため、ESP32 以外のボードへ広げる際の設計制約になりやすい。
- すでに build を `arduino-cli compile`、upload を `arduino-cli upload` に置き換える方向性は見えている。
- そのため、Arduino 向け build / upload だけを独立責務として切り出し、テスト実行時の DUT 接続と expect は `pytest-embedded` の汎用機能を活かす新規プラグインとして設計する。

## 3. プロダクト概要

- パッケージ名: `pytest-embedded-arduino-cli`
- 説明: `A pytest plugin to test Arduino projects using pytest-embedded and arduino-cli`
- 種別:
  - Python パッケージ
  - pytest plugin
- 想定利用者:
  - Arduino CLI ベースでビルド / 書き込みしたい利用者
  - `pytest-embedded` の serial / expect を使ってボード実機テストを行いたい利用者
  - ESP32 専用ではなく、将来的に複数 Arduino 対応ボードへ拡張したい利用者

## 4. 設計原則

### 4.1 中核方針

- `pytest-embedded` を土台にする
- `pytest-embedded-arduino` には依存しない
- build は `arduino-cli compile`
- upload は `arduino-cli upload`
- テスト runtime は `pytest-embedded` の汎用 DUT / serial / expect を利用する
- ESP 固有クラスや ESP 固有サービスに依存しない
- できるだけ generic serial ベースで構成する
- 互換再現よりも、単純で保守しやすい責務分離を優先する

### 4.2 責務分離

本プラグインは少なくとも次の責務を明確に分離する。

- plugin 層:
  - pytest plugin としてのエントリポイント
  - pytest option 登録
  - fixture 提供
  - `pytest-embedded` との接続点の定義
- app / builder 層:
  - `arduino-cli compile` の引数組み立て
  - build ディレクトリ解決
  - sketch.yaml / profile / build property の整理
- flasher 層:
  - `arduino-cli upload` の引数組み立て
  - upload port / profile / input artifact の整理
- serial 接続層:
  - 必要に応じて generic serial を包む薄いアダプタ
  - 独自実装を増やしすぎず、`pytest-embedded` の既存 serial 基盤を優先活用する

## 5. スコープ

### 5.1 本仕様に含める

- 公開可能な独立 Python パッケージ構成
- `src` レイアウト
- pytest plugin entry point の定義
- `arduino-cli compile` を呼ぶ build 機構
- `arduino-cli upload` を呼ぶ upload 機構
- pytest option の追加
- `pytest-embedded` の core / serial / expect を前提とした DUT 接続設計
- コマンド生成と option 解釈を検証する単体テスト
- plugin 読み込み確認の最小統合テスト
- README と examples
- Arduino 側テストライブラリ `ArduTest` と連携する `arduino_test` fixture の設計

### 5.2 本仕様に含めない

- `pytest-embedded-arduino` 完全互換
- ESP 固有機能
  - erase-all
  - chip target 前提の board 解釈
  - ESP ROM / monitor 特有挙動
- 複雑な board ごとの専用 upload strategy
- `arduino-cli board list` 連携や自動ポート解決の高度化
- ボード定義ごとの artifact 自動探索の最適化
- 並列デバイス制御や device farm 機能

### 5.3 関連仕様

`ArduTest` と `arduino_test` fixture の通信 protocol、初期同期、実行制御、成果物収集の詳細は [`ARDUTEST_PROTOCOL_SPEC.ja.md`](ARDUTEST_PROTOCOL_SPEC.ja.md) で管理する。

`arduino_test` fixture の公開 API、設定解決、pytest result への反映、artifact 保存など pytest 側の詳細は [`ARDUTEST_PYTEST_SPEC.ja.md`](ARDUTEST_PYTEST_SPEC.ja.md) で管理する。

## 6. 想定ユースケース

### 6.1 基本ユースケース

利用者は pytest 実行時に次を行えること。

1. Arduino sketch を `arduino-cli compile` でビルドする
2. ビルド成果物を `arduino-cli upload` で書き込む
3. シリアルポート経由で DUT に接続する
4. `dut.expect(...)` など `pytest-embedded` の標準的なインターフェースでテストする

host machine 上で sketch を実行する board core では、物理 serial port の代わりに TCP/IP socket 経由で DUT に接続できること。
この場合も Python テスト側は `dut.expect(...)` や `dut.write(...)` を使い、実機 serial と近い形で簡易テストできること。

### 6.2 実行モード

少なくとも次のモードを想定する。

- build + test
- build only
- test only

`test only` の場合、既存 build artifact を再利用し、upload を行った上で test を実行する。

### 6.3 テスト対象の解決規則

Arduino sketch と pytest テストを同じディレクトリに置く運用を前提とする。

- `.py` と `.ino` は同じディレクトリに配置する
- pytest をディレクトリ単位で実行した場合は、その配下のテスト対象を順に扱う
- pytest に特定の `.py` を渡した場合は、その `.py` が置かれたディレクトリの `.ino` を対象とする
- sketch の compile 条件は `sketch.yaml` から解決する

sketch の場所を CLI option で明示指定する前提は持ち込まない。

同じディレクトリの `sketch.yaml` に記載された profile だけを、その sketch が対応する profile とみなす。
対応していない profile を `--profile` で指定された場合、その sketch は build 前に skip 対象として扱う。

### 6.4 peer DUT を使う複数台テスト

複数台の DUT を使うテストでは、通常の test/sketch ディレクトリ直下に `peer_<name>` ディレクトリを置けるものとする。

例:

```text
host_smoke/
  host_smoke.ino
  sketch.yaml
  test_host_smoke.py
  peer_echo/
    peer_echo.ino
    sketch.yaml
  peer_bridge/
    peer_bridge.ino
    sketch.yaml
```

- test/sketch ディレクトリ直下の sketch は primary DUT とし、既存通り `dut` fixture で扱う
- `peer_<name>` ディレクトリは peer DUT とし、`peers["<name>"]` で参照できる
- `peer_*` ディレクトリはそれぞれ独立した Arduino sketch ディレクトリとして扱う
- peer DUT ごとに `.ino` と `sketch.yaml` を持つ
- `sketch.yaml` は Arduino CLI の規定フォーマットとして扱い、peer DUT 用の独自項目は追加しない
- peer DUT 用の追加設定ファイルは導入しない

テスト例:

```python
def test_round_trip(dut, peers):
    echo = peers["echo"]

    dut.expect_exact("main ready")
    echo.expect_exact("echo ready")
```

peer DUT の準備は、原則として `peers` fixture を要求したテストでのみ行う。
同じ module 内に `dut` だけを使うテストがある場合、そのテストのために peer DUT を build / upload / connect しない。
`peers` fixture を要求した時点で peer DUT を使うテストとみなし、`peers["<name>"]` がテスト関数内で参照されるかどうかは有効化条件にしない。
これは、peer DUT が自律的に動作し、primary DUT 側からの観測だけで検証するテストを許容するためである。

同じ sketch を複数台へ書き込む場合は、`peer_sensor1`、`peer_sensor2` のように peer ディレクトリを分ける。
設定ファイルを増やさない方針を優先し、初期仕様では同一 sketch path を複数 peer へ割り当てるための alias 設定は持たない。

## 7. 依存関係

### 7.1 runtime dependencies

少なくとも次を通常依存として含める。

- `pytest`
- `pytest-embedded`

`pytest-embedded` は dev dependency ではなく runtime dependency とする。

### 7.2 外部コマンド依存

- `arduino-cli` が実行環境にインストールされていること

`arduino-cli` 本体のインストールや board core 導入までは本プラグインの責務に含めない。

## 8. パッケージ構成要件

最低限、次のような構成を持つ。

```text
pyproject.toml
README.md
SPEC.ja.md
src/
  pytest_embedded_arduino_cli/
    __init__.py
    plugin.py
    app.py
    flasher.py
    serial.py        # 必要な場合のみ
tests/
examples/
```

補助モジュール追加は許容するが、責務を増やしすぎないこと。

## 9. pytest plugin 要件

### 9.1 entry point

`pyproject.toml` に pytest plugin の entry point を定義する。

想定例:

- group: `pytest11`
- name: `embedded-arduino-cli`
- value: `pytest_embedded_arduino_cli.plugin`

### 9.2 plugin の責務

`plugin.py` は次を担う。

- pytest option の登録
- セッション / モジュール / 関数単位で必要な fixture を提供
- build / upload の実行制御
- `pytest-embedded` と連携するための fixture を露出
- 将来サービス分離しやすいよう、CLI 実行や引数構築を他モジュールへ委譲

### 9.3 plugin の非責務

`plugin.py` 自体に長大なコマンド組み立てロジックを持たせない。

## 10. App / Builder 要件

### 10.1 目的

`arduino-cli compile` 実行に必要な情報を整理し、安定したコマンド生成 API を提供する。

### 10.2 主要責務

- テストファイル位置に基づく sketch ディレクトリ解決
- build path 解決
- `sketch.yaml` と profile に基づく compile 条件の保持
- `build_config.toml` に基づく compile-time define / flag 注入
- compile command の生成
- subprocess 実行の薄いラッパ
- テストしやすいよう、コマンド生成と実行を分離

### 10.3 扱う入力

- build path
- profile
- board options / build properties
- extra compile args
- clean build の有無

主入力は次とする。

- テストファイルの配置場所
- `sketch.yaml`
- `--profile`
- 必要に応じて環境変数

### 10.4 profile 対応範囲の扱い

`sketch.yaml` に書かれている profile は、その sketch が対応する profile 一覧である。

期待する挙動は次のとおり。

1. `--profile` が指定され、その値が `sketch.yaml` に存在する場合はその profile を使う
2. `--profile` が指定され、その値が `sketch.yaml` に存在しない場合は、その sketch を skip する
3. `--profile` が未指定で `default_profile` が定義されている場合はそれを使う
4. `--profile` が未指定で profile が 1 つだけならそれを自動選択する
5. `--profile` が未指定で profile が複数あり `default_profile` もない場合は設定不備としてエラーにする

この設計により、対応 profile だけを `sketch.yaml` に記述するのが正しい構成となる。
非対応 profile を無理に列挙し、Python 側で `pytest.skip()` する構成は推奨しない。

### 10.5 `build_config.toml`

必要に応じて sketch ディレクトリに `build_config.toml` を置けるものとする。

想定用途:

- Wi-Fi SSID / password
- API endpoint
- テスト用フラグ

このファイルは、環境変数名と compile-time define 名の対応、および値なし compile-time flag を定義するために使う。

想定例:

```toml
[defines]
TEST_WIFI_SSID = "WIFI_SSID"
TEST_WIFI_PASSWORD = "WIFI_PASSWORD"

[flags]
PYTEST_BUILD = true
ENABLE_TEST_HOOKS = true
```

`[defines]` は、左辺を環境変数名、右辺を C/C++ 側の define 名として扱う。
plugin は指定された環境変数を読み、`-D<define名>="<環境変数値>"` の形で `arduino-cli compile --build-property build.extra_flags=...` に変換して渡す。
環境変数が未設定でも、その define には空文字を渡す。

`[flags]` は、値なし define を明示するために使う。
左辺を C/C++ 側の macro 名、右辺を boolean として扱い、`true` の項目だけ `-D<macro名>` に変換する。
`false` の項目は出力しない。
boolean 以外の値は設定不備としてエラーにする。

`PYTEST_BUILD` のようなテスト用 flag は、plugin が自動付与しない。
本番 code path と異なるものを暗黙にテストすることを避けるため、必要な project が `build_config.toml` の `[flags]` で明示する。

`.env` ファイルの自動読込は本仕様には含めない。

### 10.6 コマンド生成方針

- コマンド生成は pure に近い関数または dataclass ベース API とする
- 実コマンド実行は別メソッドまたは別関数に分ける
- テストでは subprocess 実行よりコマンド配列の検証を中心に行う

## 11. Flasher 要件

### 11.1 目的

`arduino-cli upload` 実行に必要な情報を整理し、upload の責務を build と分離する。

### 11.2 主要責務

- upload 対象 build path の解決
- port / protocol / profile など upload 条件の保持
- upload command の生成
- subprocess 実行の薄いラッパ

### 11.3 扱う入力

- build path
- port
- profile
- extra upload args

### 11.4 方針

- build artifact の生成責務を持たない
- upload だけに集中する
- board 固有最適化を初期段階では入れない
- `--port=socket://...` のような runtime 接続先は、`arduino-cli upload --port` には渡さない
- upload 後に runtime 接続先の補完が必要な場合は、DUT / Serial 連携層で扱う

## 12. DUT / Serial 連携要件

### 12.1 基本方針

- DUT・serial・expect は `pytest-embedded` の既存 generic 機能を活用する
- `EspSerial` や ESP 向け専用クラスには依存しない

### 12.2 設計意図

- build / upload と test runtime を分離する
- テストランタイム側はできるだけ board 非依存で保つ
- 将来、必要に応じて board family ごとの差分を upload strategy または service 層へ切り出せるようにする

### 12.3 到達点

- generic serial で接続できる前提のボードでテスト可能
- `pytest-embedded` 標準 DUT を使った `expect` ベースの基本テストが成立する
- profile ごとに異なる serial port を環境変数から解決できる
- host machine 上で動作する board core では、pyserial の `socket://` URL を使って TCP/IP 経由で DUT に接続できる

### 12.4 host Arduino core の socket 接続

host machine 上で Arduino sketch を実行する board core では、`--port=socket://localhost` のような port 番号なし socket URL を指定できるものとする。

この場合の流れ:

1. `arduino-cli compile` で host 実行ファイルをビルドする
2. `arduino-cli upload` で host 実行ファイルを起動する
3. build 出力ディレクトリ配下の `*.host-arduino.json` を探索する
4. JSON の `port` を読み取る
5. `socket://localhost:<port>` のように runtime 接続先を補完する
6. `pytest-embedded-serial` / pyserial の socket URL として DUT に接続する

host-arduino 情報ファイルの想定 schema:

```json
{
  "pid": 21228,
  "port": 56789
}
```

`port` は 1 以上 65535 以下の整数であること。
`pid` は初期実装では必須利用しないが、将来の cleanup や診断用途で利用できる。

`socket://localhost:56789` のように port 番号まで指定された場合は、JSON 探索による補完を行わず、その URL をそのまま runtime 接続先として使う。

`--flash-port` が指定された場合は既存の port 優先順位に従い、upload 用 port として優先する。
host Arduino core の socket 実行では、通常 `--flash-port` は使わず `--port=socket://...` を使う運用を想定する。

upload の標準出力に `HOST_ARDUINO_PORT=...` が出る場合でも、plugin は stdout capture を必須にしない。
既存の upload 表示挙動を変えないため、port 解決は build 出力ディレクトリの `*.host-arduino.json` を優先する。

host 実行は純粋なロジックや serial protocol の簡易確認用であり、実機テストの代替ではない。
OS、gcc などの toolchain version、host core の `Serial` class 実装差により結果が変わる可能性がある。
peripheral、timing、割り込み、Flash/NVS、board 固有 API は実機で確認する。
また、本番で使う board profile での build test は別途行うことを推奨する。

### 12.5 skip の責務分担

本プラグインは、profile 非対応による skip を build 前に判定できるべきである。

- `sketch.yaml` に存在しない profile を指定された場合は、その sketch を compile / upload 前に skip する
- この skip は test 関数内の `pytest.skip()` に依存しない

一方で、同じ profile でも実機状態や外部条件によって実行不能になるケースはテスト側で `pytest.skip()` を使ってよい。
例えば Wi-Fi 接続条件や外部サービス条件のような runtime 条件は、Python テスト側で扱ってよい。

### 12.6 peer DUT の profile 解決

peer DUT の profile は、各 `peer_<name>/sketch.yaml` を基準に解決する。

peer DUT の profile 解決順は次の通り。

1. `--peer-profile <name>:<profile>`
2. `peer_<name>/sketch.yaml` の `default_profile`
3. 決まらなければ、その peer DUT を必要とするテストを skip する

`--profile` は primary DUT 専用とし、peer DUT の profile 解決には使わない。
peer DUT では、profile が 1 つだけの場合でも自動選択しない。
これは、重い複数台テストが意図せず実行されることを避けるためである。

`--peer-profile` で指定された profile が peer DUT の `sketch.yaml` に存在しない場合は、その peer DUT を必要とするテストを skip する。

peer DUT は重い複数台テストで使われることが多いため、無指定で動かしたくない peer sketch では `default_profile` を定義しない。
この場合、`--peer-profile` が指定されなければ、`peers` fixture を使うテストは skip される。

### 12.7 peer DUT の port 解決

`--port` と `--flash-port` は primary DUT 専用とする。
peer DUT の port は peer 名に基づいて解決し、primary DUT の port 指定を暗黙に流用しない。

peer DUT の runtime port 解決順は次の通り。

1. `--peer-port <name>:<port>`
2. `TEST_SERIAL_PORT_PEER_<NAME>_<PROFILE>`
3. `TEST_SERIAL_PORT_PEER_<NAME>`
4. `peer_<name>/sketch.yaml` の `profiles.<profile>.port` が `socket://...` URL の場合
5. 解決できなければ、その peer DUT を必要とするテストを skip する

`<NAME>` と `<PROFILE>` は大文字化し、`-` を `_` に置換した形式とする。
例えば `peer_echo` の `host` profile では `TEST_SERIAL_PORT_PEER_ECHO_HOST` を参照する。

peer DUT の upload port 解決では、runtime port が `socket://...` URL の場合は `arduino-cli upload --port` へ渡さない。
これは primary DUT と同じく、socket URL を runtime 接続先として扱うためである。

peer DUT でも host Arduino core の port 番号なし socket URL を使える。
`socket://localhost` のような URL は、該当 peer DUT の upload 後に、その peer DUT の build 出力ディレクトリ配下の `*.host-arduino.json` から `port` を読み取って補完する。

### 12.8 peer DUT の build / upload / connect

peer DUT の build path は、各 peer sketch ディレクトリ配下の `<peer_dir>/build/<profile or default>` とする。
primary DUT の build path と peer DUT の build path は分離する。

`peers` fixture が要求された場合、plugin は検出された peer DUT について build / upload / runtime port 補完 / 接続を行う。
`peers["<name>"]` は接続済み peer DUT を参照するための mapping API であり、参照された peer だけを遅延起動する仕様にはしない。

- `--run-mode=all`: peer DUT を build し、upload してから test を実行する
- `--run-mode=build`: peer DUT を build し、test 実行は skip する。この場合 peer port は不要
- `--run-mode=test`: 既存 build artifact を使って peer DUT を upload してから test を実行する

upload / connect の順序は次の通りとする。

1. primary DUT を build / upload する
2. `peers` fixture が要求された場合、検出された peer DUT を名前順で build / upload する
3. peer DUT の runtime port 補完を行う
4. peer DUT に接続し、`peers["<name>"]` として提供する
5. pytest-embedded の通常処理により primary DUT に接続し、`dut` として提供する

この順序では、実機 DUT が upload 直後に短時間だけ出力する起動メッセージを Python 側が取りこぼす可能性がある。
host Arduino core のように出力が socket 接続まで保持される環境では問題になりにくいが、一般の実機 serial では sketch 側で十分な待機、再送、または Python 側からの入力を待つ handshake を用意することを推奨する。
特に peer DUT では、`peers` fixture が要求された時点で検出済み peer をすべて起動するため、DUT 間の起動順に依存するテストは sketch 側 protocol で同期する。

peer DUT の構造不備は設定エラーとして扱う。
例えば `.ino` がない、`.ino` が複数ある、`sketch.yaml` が壊れている場合は error とする。
一方で、profile 非対応、profile 未決定、port 未解決のように実行条件が揃わない場合は skip とする。

## 13. pytest option 要件

少なくとも次のカテゴリの option を対象とする。

### 13.1 実行モード

- build するか
- upload するか
- test を実行するか

例:

- `--run-mode=all|build|test`

意味は次の通り。

- `all`: build → upload → test
- `build`: build のみ
- `test`: 既存 build artifact を使って upload → test

### 13.2 Arduino CLI compile 関連

- profile

本プラグイン固有の compile 関連 option は `--profile` のみとする。
build path は `<sketch_dir>/build/<profile or default>` に固定し、MVP では override を持たない。

build 実行前に profile 対応可否を判定し、非対応 profile の sketch では compile を行わない。

### 13.3 Arduino CLI upload 関連

本プラグイン固有の upload 関連 option は追加しない。
upload に必要な port 指定は `pytest-embedded` 標準の `--flash-port` または `--port` を使う。
ただし、`--port=socket://...` は runtime 接続先を表すため、`arduino-cli upload --port` には渡さない。

### 13.4 peer DUT 関連

peer DUT 個別指定のため、次の option を追加する。

- `--peer-profile <name>:<profile>`
- `--peer-port <name>:<port>`

どちらも複数回指定できる。

例:

```bash
pytest tests/foo \
  --peer-profile echo:host \
  --peer-profile bridge:esp32 \
  --peer-port echo:socket://localhost \
  --peer-port bridge:/dev/ttyUSB1
```

`--peer-profile` と `--peer-port` の値は `<peer-name>:<value>` 形式とする。
`,` 区切りの複数指定は採用せず、複数 peer を指定する場合は option を複数回書く。

`:` が含まれない値は error とする。
同じ peer 名が同一 option で複数回指定された場合は error とする。
存在しない peer 名が指定された場合も error とする。

`--peer-profile` は該当 peer DUT の profile 解決だけに影響する。
`--peer-port` は該当 peer DUT の runtime port / upload port 解決だけに影響する。
primary DUT の `--profile`、`--port`、`--flash-port` の挙動は既存通り維持する。

### 13.5 serial / DUT 関連

- `pytest-embedded` 標準 option を活かす
- 必要に応じて plugin 側で橋渡しする
- 少なくとも `--port`、`--flash-port`、`--baud`、`--embedded-services` を前提とする

serial port は次の優先順で解決できるようにする。

1. `--flash-port`
2. `--port`
3. profile ごとの環境変数
4. 共通環境変数

profile ごとの環境変数名は、例えば `TEST_SERIAL_PORT_ESP32S3` のように profile 名を正規化した形式とする。
共通環境変数は `TEST_SERIAL_PORT` とする。

`--port` または環境変数に `socket://localhost` のような socket URL が指定された場合は、runtime 接続先として扱う。
port 番号なしの socket URL は、upload 後に build 出力ディレクトリの `*.host-arduino.json` から `port` を読み取って補完する。
port 番号ありの socket URL は補完せず、そのまま使う。

### 13.6 pytest 標準 verbosity 連携

- 追加の専用 verbose option は設けない
- pytest 標準の `-v` / `-vv` に従って build / upload のログ出力量を変える
- `-v` では `arduino-cli compile` / `arduino-cli upload` の実行コマンドを表示する
- `-vv` では上記に加えて `cwd`、`sketch_dir`、`build_path`、`profile`、`port` などの実行文脈も表示する

build 前 skip が発生した場合、`-v` 以上では非対応 profile により skip したことが分かる出力を持つことが望ましい。
peer DUT の build / upload でも、`-v` / `-vv` のログには peer 名が分かる情報を含める。

### 13.7 option 設計方針

- 命名は `arduino-cli` の用語を優先する
- ESP 固有用語を option 名に持ち込まない
- pytest-embedded 既存 option と競合しにくい名前にする
- build / upload / runtime の責務境界が option 名から見えるようにする
- plugin 固有 option は、基本実行用の `--run-mode` / `--profile` と、peer DUT 用の `--peer-profile` / `--peer-port` に絞る

## 14. テスト状態保存要件

### 14.1 目的と位置付け

pytest で実行したマイコン向け実機テストについて、各テストの検証状態をローカルファイルに保存する。

主目的は、ローカル開発中に「最後にいつ成功したか」「前回の結果はどうだったか」を確認できるようにすることである。

本機能は「実機 verification state cache」として扱い、以下は対象外である。

- テストレポート、長期履歴管理、CIダッシュボード、品質ゲート
- 実行履歴の蓄積、メトリクス収集、trend 分析
- build artifact、ログ、シリアル出力、スクリーンショットなどの artifact 保存
- stale entry の自動削除や rename 検出

state cache は実行環境に応じてリセットしてもテスト本体やビルドに影響しない disposable なファイルである。

### 14.2 基本方針

- state は実機上で実際に verification が行われた場合のみ更新する
- 認識単位は `(profile_name, nodeid)` の組とする
- profile ごとに別ファイルへ分割することは初期仕様に含めない
- state.json は current state cache であり、append-only history は保持しない
- pytest collection との完全一致を保証しない
- stale entry が残ることを許容する

### 14.3 保存先と構成

#### 14.3.1 ディレクトリ設定

状態保存ディレクトリは CLI option で指定可能とする。

- option: `--save-state-dir`
- default: `.pytest-results`
- absolute path または relative path（pytest rootdir 基準）を指定可能
- git 管理外とすることを推奨し、`.gitignore` への追加を推奨する

#### 14.3.2 ファイル構成

- state は `<save_state_dir>/state.json` に保存する
- `<save_state_dir>/` はローカル状態保存用ディレクトリとして扱う
- 将来の拡張用に他のキャッシュファイルを置ける構造を想定するが、初期仕様では `state.json` のみ

#### 14.3.3 state.json 構造

```json
{
  "schema_version": 1,
  "updated_at": "2026-05-10T20:00:00+09:00",
  "profiles": {
    "uno": {
      "tests": {
        "tests/test_gpio.py::test_led": {
          "last_result": "passed",
          "last_run_at": "2026-05-10T20:00:00+09:00",
          "last_success_at": "2026-05-10T20:00:00+09:00"
        }
      }
    },
    "esp32": {
      "tests": {
        "tests/test_gpio.py::test_led": {
          "last_result": "failed",
          "last_run_at": "2026-05-10T20:05:00+09:00",
          "last_success_at": "2026-05-09T18:30:00+09:00"
        }
      }
    }
  }
}
```

- 内部では profile 名を親キーとして管理する
- 各 profile の配下に、pytest の `nodeid` をキーとしたテスト状態を保存する
- profile 名には、実際に使用された最終的な実行 profile 名をそのまま使用する
- profile 未指定実行でも、内部選択された最終 profile 名を使用する
- synthetic/default profile 名は使用しない

### 14.4 保存内容

各テストについて、少なくとも以下を保存する。

- `last_result`: 最終結果（`passed`、`failed`、`error` など）
- `last_run_at`: 最終実行日時（ISO8601 形式、タイムゾーン付き）
- `last_success_at`: 最終成功日時（ISO8601 形式、タイムゾーン付き）

- 最初に成功するまでは `last_success_at` は存在しなくてよい
- 未実行テストは `state.json` に entry が存在しないことで表現する
- JSON は人間にも読みやすく、機械にも処理しやすい形式とする

### 14.5 保存対象の判定

state を更新するのは、実機上で実際に verification が行われた場合のみである。

次の場合は state を更新しない：

- `build failed`: compile に失敗した場合
- `upload failed`: upload に失敗した場合
- 環境要因による失敗: board not found、port open failed、device unavailable など
- `skipped`、`deselected`: テストが実行されなかった場合

state を更新する場合：

- `pass`/`fail`/`error` など、実際にボード上でテストが開始された結果のみ更新対象
- upload 成功後にテスト実行へ到達した場合のみ更新対象

### 14.6 結果更新動作

- 実行されたテストだけを upsert する
- 実行されなかったテストの entry は変更しない

成功時（`pass`）：
- `last_result`、`last_run_at`、`last_success_at` を更新する

失敗時（`fail`/`error` など）：
- `last_result`、`last_run_at` のみ更新し、既存の `last_success_at` は保持する

テストの削除、rename、対象外化によって古い entry が残ってもよい。
stale entry の cleanup は初期仕様に含めない。

### 14.7 peer DUT の扱い

peer DUT を使うテストでも、state cache には primary DUT（親ディレクトリの sketch）のみの結果を保存する。

- peer DUT の build / upload 状態は記録しない
- `nodeid` は peer 名を含まない
- 同じ `nodeid` を持つテストが複数台で実行されても、state には primary DUT の結果のみ反映される

### 14.8 ArduTest との独立性

state cache 機能は ArduTest に依存しない。

- ArduTest を使わないテストでも state cache を利用できる
- ArduTest fixture の有無にかかわらず、テスト実行がボード上で行われた結果が記録される
- `pytest-embedded` 標準の expect による basic テストでも state cache に entry が作成される

### 14.9 CLI option 追加

state cache 機能を制御するため、pytest option に次を追加する。

- `--save-state`: flag 形式。指定された場合のみ state を保存する（default: 無効）
- `--save-state-dir`: 値指定形式。state.json を保存するディレクトリを指定（default: `.pytest-results`）

例：

```bash
pytest tests/foo --save-state
pytest tests/foo --save-state --save-state-dir .test-cache
```

`--save-state-dir` が指定されても `--save-state` がない場合、state は保存されない。

### 14.10 実装上の考慮

#### 14.10.1 plugin 層の責務

- pytest hook（`pytest_runtest_logreport` など）を使ってテスト結果を捕捉
- build / upload 成功の確認（失敗時は state 更新をスキップ）
- テスト実行が実機上で行われたかどうかの判定
- profile 名の確定
- nodeid の取得
- state.json の読み書き（ファイル I/O）

#### 14.10.2 ファイル I/O 設計

- state.json が存在しないとき、初期構造を自動生成する
- `<save_state_dir>/` ディレクトリが存在しないとき、自動作成する
- 複数テストの同時実行（pytest-xdist など）による race condition は、初期仕様では対応外とする
- ユーザーが state.json を削除または手動編集してもテスト本体に影響しない

#### 14.10.3 テストの判定

テスト実行が実機上で行われたかの判定基準：

- upload フェーズが成功した後、test フェーズの execution に到達したこと
- この判定は `pytest_runtest_logreport` で `when == "call"` の report を使う

#### 14.10.4 profile 名の確定

- `--profile` が明示指定された場合はその値を使用
- 自動選択（`--profile` 未指定で profile 1 つの場合）された場合、選択された profile 名を使用

### 14.11 スコープ外

- state.json の content versioning や migration 機構は初期仕様に含めない
- stale entry の自動検出・削除は行わない
- history file や long-term metrics は初期仕様に含めない
- CI 向けレポート生成や HTML 表示は初期仕様に含めない
- `sketch path` や `fqbn` のような override option は必須要件に含めない
- ログ出力制御は pytest 標準の verbosity に従わせ、専用 option を増やさない

## 14. テスト要件

### 14.1 単体テスト

少なくとも次を検証する。

- option 解釈
- build command 生成
- upload command 生成
- build path 解決
- profile / port の反映
- テストファイル位置からの sketch ディレクトリ解決
- `-v` / `-vv` に応じたログ出力の切り替え
- `build_config.toml` と環境変数からの define 生成
- `build_config.toml` の `[flags]` からの値なし define 生成
- profile ごとの serial port 解決
- `socket://localhost` のような host 実行向け runtime port 補完
- `*.host-arduino.json` からの port 読み取り
- socket URL を upload port に渡さないこと
- 非対応 profile 指定時の build 前 skip
- `default_profile` と単一 profile 自動選択の解決
- `peer_*` ディレクトリから peer DUT を検出できること
- `peers["<name>"]` の名前解決
- `--peer-profile <name>:<profile>` の複数回指定と重複指定 error
- `--peer-port <name>:<port>` の複数回指定と重複指定 error
- peer DUT の profile 解決順
- peer DUT の port 解決順
- peer DUT の profile 未決定 / port 未解決による skip
- `peers` fixture を使わないテストでは peer DUT を準備しないこと

### 14.2 最小統合テスト

少なくとも次を検証する。

- pytest plugin としてロードできること
- `pytest --help` または plugin manager 上で option が見えること
- fixture が解決できること

### 14.3 テスト方針

- 実機依存を避ける
- `subprocess.run` はモック可能な設計にする
- Arduino CLI 実行の成否よりも、まずは責務分離とインターフェース安定性を検証する
- verbosity 連携の検証では、標準出力そのものではなく plugin 内のログ分岐を確認してよい

## 15. examples 要件

`examples/` には最小利用例を含める。

最低限必要な内容:

- 最小 sketch 例
- 最小 pytest テスト例
- 実行コマンド例
- 必要なら `pytest.ini` または CLI 指定例

目的は「最小の build / upload / serial expect のつながり」を示すこととする。

host Arduino core 向けの example では、次を示すこと。

- `lang-ship:host:host` のような host 実行 profile
- `--port=socket://localhost` による TCP/IP 経由の DUT 接続
- `*.host-arduino.json` の `port` を使った socket URL 補完
- host 実行は純粋なロジックや serial protocol の簡易確認向けで、実機テストや本物の board profile による build test の代替ではないこと

peer DUT 向けの example では、次を示すこと。

- `peer_<name>` ディレクトリによる peer DUT の自動検出
- `peers["<name>"]` による peer DUT 参照
- `--peer-profile` / `--peer-port` による peer DUT 個別指定
- `default_profile` を持つ peer は無指定でも動作し、持たない peer は明示 profile 指定時だけ動作すること

## 16. README 要件

README には少なくとも次を含める。

- 概要
- 何を解決する plugin か
- `pytest-embedded-arduino` と何が違うか
- インストール方法
- 前提条件
  - `arduino-cli`
  - board core
  - serial port
- 基本的な使い方
- 最小のテスト例
- 主要 option
- `-v` / `-vv` 時のログ挙動
- 設計方針
- 今後の拡張候補

## 17. 非機能要件

### 17.1 保守性

- モジュール境界が明確であること
- subprocess 実行とコマンド生成が分離されていること
- board 固有処理を混在させないこと

### 17.2 拡張性

- 将来 service 層や strategy 層へ切り出しやすいこと
- upload 実装を board family ごとに差し替えやすいこと
- build property や artifact 解決ルールを追加しやすいこと

### 17.3 可搬性

- 少なくとも Linux / macOS を前提に不自然な前提を持たないこと
- シリアルポートや CLI パスの扱いで特定環境に強く依存しすぎないこと

## 18. 参考実装から取り込む観点

参照対象:

- `https://github.com/tanakamasayuki/pytest-esp32-lib/blob/main/tests/conftest.py`

ここから参考にする観点は次の通り。

- `run-mode` の概念
- profile に応じた build path 分離
- `sketch.yaml` と `-m/--profile` を中心にした build 実行
- `arduino-cli compile` / `upload` のシンプルな実行モデル
- build only 時に Python 側テスト実行を skip する考え方
- runner ごとに `.ino` と同じ場所へ `sketch.yaml` を置く構成

一方で、そのまま固定化しない方針は次の通り。

- プロジェクト個別の dotenv 前提
- ESP32 前提の運用ノウハウ
- `pytest-embedded-arduino` 由来の制約を前提とした option 設計
- conftest にすべて集約する構成

## 19. API / 実装イメージ

実装詳細は後続設計で調整しうるが、次のような薄い構造を想定する。

- `app.py`
  - `ArduinoCliApp`
  - `ArduinoCliBuildConfig`
  - `build_command()`
  - `compile()`
- `flasher.py`
  - `ArduinoCliFlasher`
  - `ArduinoCliUploadConfig`
  - `upload_command()`
  - `upload()`
- `plugin.py`
  - `pytest_addoption()`
  - build/upload 実行 fixture
  - `pytest-embedded` 連携 fixture

この段階では API 名は仮であり、実装時に Python パッケージとして自然な形へ調整してよい。

## 21. 受け入れ条件

本仕様の受け入れ条件は次の通り。

1. `pytest-embedded-arduino-cli` が Python パッケージとしてインストール可能である
2. pytest plugin として自動ロードまたは明示ロードできる
3. `arduino-cli compile` を呼ぶ build 層が存在する
4. `arduino-cli upload` を呼ぶ flasher 層が存在する
5. `pytest-embedded` ベースで DUT / serial / expect を利用する基本設計になっている
6. ESP 固有依存が入っていない
7. 最低限の単体テストと plugin 読み込みテストが存在する
8. README と examples が存在する
9. `sketch.yaml` に存在しない profile を指定した sketch は build 前に skip される
10. `peer_*` ディレクトリを使った複数 DUT テスト仕様が定義されている
11. peer DUT の profile / port を名前付きで指定できる
12. `--save-state` option で state cache 保存の有効/無効を制御できる
13. `--save-state-dir` option で state.json の保存先を指定できる
14. state.json に `(profile_name, nodeid)` 単位でテスト状態が記録される
15. 実機上で実行されたテストのみ state.json に entry が作成される
16. peer DUT の state は記録されず、primary DUT のみ記録される
17. ArduTest に依存せず、基本的な pytest-embedded テストでも state cache が機能する

## 22. 今後の拡張候補

- board family ごとの upload strategy 差し替え
- `arduino-cli board list` 連携によるポート解決支援
- artifact 自動探索と board ごとの差分吸収
- monitor / reset 制御の抽象化
- build profile と test matrix の統合
- `fqbn` override や sketch path override の追加
- board core / fqbn ごとの capability 宣言

以上を本プロジェクトの仕様とする。
