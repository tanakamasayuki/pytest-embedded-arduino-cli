# pytest-embedded-arduino-cli 仕様書

[English](SPEC.md)

## 1. 文書の目的

本書は、新規 Python パッケージ / pytest plugin `pytest-embedded-arduino-cli` の要件を整理するための仕様書である。

本プラグインは `pytest-embedded` の core / serial / expect を土台にしつつ、Arduino 向けの build / upload を `arduino-cli` ベースで提供することを目的とする。

明示指定による複数 profile / peer 組合せ実行と収集時の適用条件判定は [24 章](#24-明示指定による複数-profile--peer-組合せ実行) に記載する。

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
- 同じ物理 serial device の upload / test 同時利用を防ぐ device lock 機構
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
- 同一 device 排他を超える device farm 機能

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

peer DUT の upload / connect は、原則として `peers` fixture を要求したテストでのみ行う。
`peer_*` ディレクトリが存在する場合、すべての compile を upload より前に終えるため、primary upload より前に peer sketch を compile してよい。
`peers` fixture を要求した時点で peer DUT を使うテストとみなし、`peers["<name>"]` がテスト関数内で参照されるかどうかは有効化条件にしない。
これは、peer DUT が自律的に動作し、primary DUT 側からの観測だけで検証するテストを許容するためである。

同じ sketch を複数台へ書き込む場合は、`peer_sensor1`、`peer_sensor2` のように peer ディレクトリを分ける。
設定ファイルを増やさない方針を優先し、初期仕様では同一 sketch path を複数 peer へ割り当てるための alias 設定は持たない。

## 7. 依存関係

### 7.1 runtime dependencies

少なくとも次を通常依存として含める。

- `pytest`
- `pytest-embedded` と `pytest-embedded-serial` の 2.8 以降

`pytest-embedded` は dev dependency ではなく runtime dependency とする。

plugin は `pytest-embedded` の private な部分を使う。peer DUT を作るための `_listener_gn`、`_pexpect_fr_gn`、`pexpect_proc_fn` と、`socket://` / `arduinomonitor://` の port のための `_SerialRedirectThread` の差し替えである。下限はこれらを試験した版とする。`pytest-embedded` の新しいリリースで plugin の更新が要ることがある。

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
plugin は指定された環境変数を読み、`-D<define名>="<環境変数値>"` の形で `arduino-cli compile --build-property <property>=...` に変換して渡す。
環境変数が未設定でも、その define には空文字を渡す。

`[flags]` は、値なし define を明示するために使う。
左辺を C/C++ 側の macro 名、右辺を boolean として扱い、`true` の項目だけ `-D<macro名>` に変換する。
`false` の項目は出力しない。
boolean 以外の値は設定不備としてエラーにする。

`PYTEST_BUILD` のようなテスト用 flag は、plugin が自動付与しない。
本番 code path と異なるものを暗黙にテストすることを避けるため、必要な project が `build_config.toml` の `[flags]` で明示する。

#### 投入先プロパティの選択

`--build-property X=Y` は追記ではなく**置換**なので、投入先には platform が空にしているプロパティを選ぶ必要がある（さもないと platform 定義の flag を消してしまう）。host / AVR では `build.extra_flags` が空であることが多いが、ESP32 では platform が値を入れており、さらに一部の ESP32 board option は `build.defines` にも値を入れる。

そこで plugin は、defines/flags がある時だけ、かつ compile する時（`--run-mode=all` / `build`）だけ、投入先を自動選択する。

1. ビルド対象と同じ sketch / profile に対し `arduino-cli compile --show-properties` で展開済みプロパティを調べる。
2. `build.extra_flags` → `build.defines` → `compiler.cpp.extra_flags` と `compiler.c.extra_flags` の両方 → `compiler.cpp.extra_flags` の順に、**存在して空の最初の候補グループ**を採用する。広い範囲に効く build-level property が安全ならそれを使い、ESP32 の board 設定で埋まっている場合は C/C++ compile flags に fallback する。
3. どの候補グループも空でなければ、clobber を起こすビルドを cryptic に失敗させず、compile 前に（非空の値を提示して）明確なエラーを出す。

defines/flags が無い場合、手動 override がある場合（下記）、`--run-mode=test` の場合はプローブを行わない。

project は `build_config.toml` で投入先を明示でき、その場合プローブを省略する（約1秒速くなる）。

```toml
build_property = "build.defines"        # 全 profile 共通の既定

[profiles.esp32]
build_property = "build.defines"        # profile 別の override（解決後 profile 名）
```

優先順位: profile 別 `[profiles.<name>].build_property` > トップレベル `build_property` > 自動検出。

`.env` ファイルの自動読込は本仕様には含めない。

### 10.6 コマンド生成方針

- コマンド生成は pure に近い関数または dataclass ベース API とする
- 実コマンド実行は別メソッドまたは別関数に分ける
- テストでは subprocess 実行よりコマンド配列の検証を中心に行う

### 10.7 `sketch.yaml` について plugin が約束すること

plugin 自身が読む `sketch.yaml` のキーは少ない。それ以外は `--profile` / `-m` を通して arduino-cli に届き、その振る舞いは arduino-cli のものであって、この plugin の契約ではない。

plugin が読んで解釈するもの:

- `profiles` の名前と `default_profile`。profile の選択に使う（10.4、および profile が 1 つのときの自動選択）
- `profiles.<profile>.port`。runtime と upload の port の最後の候補として使う（14.5、13.7）
- `profiles.<profile>.fqbn` と `profiles.<profile>.platforms`。sketch 間で pluggable monitor の判定を共有するために、まるごと比べるだけに使う（13.9）。中身の意味は解釈しない

profile 名は、別々の port 変数にならなければならない。次を設定エラーとする。

- 1 つの `sketch.yaml` の中で、大文字化して `-` を `_` に置換すると同じ名前になる 2 つの profile。例えば `esp32-s3` と `esp32_s3`
- 名前が `PEER_...` になる profile。`TEST_SERIAL_PORT_PEER_...` は peer DUT のものであるため

arduino-cli に渡すだけで、plugin は約束しないもの:

- `port_config`、board option、programmer、platform の解決。版を書かない `platforms` の項目も含む
- top-level の `default_port_config`。profile を選んだとき arduino-cli は適用しない
- `arduino-cli monitor` 経由で読む runtime の port には `--baud` は効かない。設定は arduino-cli から来る

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

## 12. Device Lock 要件

### 12.1 目的

複数の pytest process が 1 つまたは複数の project から同時に実行された場合でも、同じ物理 DUT に対して同時に upload したり、テスト実行中の DUT を別 process が書き換えたりしないようにする。

この lock は物理 device 利用のためのものであり、compile のためのものではない。
build は device lock 待機より前に実行できる状態を維持する。

### 12.2 lock 対象

既定の lock key は、解決済みの物理 serial port とする。

- primary DUT では、通常の `--flash-port`、`--port`、環境変数の優先順位に従って解決された upload / runtime 用 serial port を使う
- peer DUT では、各 peer の解決済み runtime / upload 用 serial port を使う
- profile 名は既定の lock key にしない。同じ profile 名でも project によって別 device を指すことがあり、逆に異なる profile でも同じ物理 device を指すことがあるため
- `socket://...` は通常 host process または TCP/IP DUT を表し、共有物理 serial device ではないため、既定では lock しない
- key は port の文字列とする。filesystem の path は symlink を解決する（`/dev/serial/by-id/...` は `/dev/ttyUSB0` と同じ device を lock する）。`wchlink://...` や `oep://...` のようなその他の形は書かれたまま使う。plugin には `wchlink://S` と `/dev/ttyACM3` が同じ probe であることも、2 つの `oep://` の slot が同じ hardware を共有するかも分からない。1 つの device を複数の書き方で指す project は、どの実行でも同じ `--device-lock-key` を指定する

1 つのテストで複数 peer DUT を使う場合は、`peers` fixture が要求された時点で、その peer DUT 群が必要とする全ての物理 serial lock key を収集する。
同じ peer 群の中で物理 serial key が重複した場合は設定エラーとして扱う。peer の lock key が既に保持している primary DUT の lock key と重複した場合も設定エラーとして扱う。

### 12.3 lock の取得タイミングと保持期間

plugin は compile 完了後、device を必要とする最初の upload の直前に device lock を取得する。

lock は upload、runtime serial 接続、テスト実行、primary / peer DUT の teardown を含む module 単位の DUT 利用が終わるまで保持する。
upload 直後に lock を解放すると、別 pytest process がテスト中の DUT へ新しい firmware を upload できてしまうため不十分である。

`--run-mode=build` では device lock を取得しない。
`--run-mode=all` と `--run-mode=test` では、lock 可能な物理 serial target が解決できた場合に lock を取得する。

peer DUT 群では、process 間の deadlock を避けるため、lock key のソート順で決定的に lock を取得する。
primary DUT の lock は、peer DUT が `peers` fixture を要求したテストでのみ準備される構造のため、それより前の primary upload 直前に取得する。

### 12.4 lock の保存先と stale lock

device lock は project directory 配下ではなく、user 単位の runtime または cache directory に保存する。
これにより、同じ machine 上の別 project も同じ排他 domain を共有する。
既定 directory は次の順で解決する。

1. Windows では、`LOCALAPPDATA` が設定されている場合 `%LOCALAPPDATA%\pytest-embedded-arduino-cli\locks`
2. Windows では、`APPDATA` が設定されている場合 `%APPDATA%\pytest-embedded-arduino-cli\locks`
3. Windows fallback は `~/AppData/Local/pytest-embedded-arduino-cli/locks`
4. Windows 以外では、`XDG_RUNTIME_DIR` が設定されている場合 `$XDG_RUNTIME_DIR/pytest-embedded-arduino-cli/locks`
5. Windows 以外では、`XDG_CACHE_HOME` が設定されている場合 `$XDG_CACHE_HOME/pytest-embedded-arduino-cli/locks`
6. Windows 以外の fallback は `~/.cache/pytest-embedded-arduino-cli/locks`

lock file 名は raw path text をそのまま使わず、正規化または hash 化した lock key に基づくものとする。

lock file が存在することだけで device 使用中とは判断しない。
実装は `portalocker` などの OS file lock に基づくものとし、process が強制終了された場合は OS が file descriptor を閉じることで実 lock が解放されるようにする。
強制終了後に lock file が残っていても、それは再利用可能な metadata file として扱う。

lock 保持中は、診断用 metadata を lock file に書いてよい。

- process id
- hostname
- lock key
- port
- profile
- sketch directory
- start time

この metadata は log や timeout 診断用であり、排他判定の authoritative な情報としては使わない。

### 12.5 lock option

device lock を制御するため、次の pytest option を追加する。

- `--device-lock=auto|off|required`
- `--device-lock-timeout=SECONDS`
- `--device-lock-dir=PATH`
- `--device-lock-key=KEY`

既定値は `--device-lock=auto` とする。

各 mode の意味は次の通り。

- `auto`: 物理 serial lock key が解決できた場合に lock を取得する。既定の socket URL など lock 対象外では lock せず続行する
- `off`: device lock を取得しない
- `required`: upload/test run で lock key が必須。lock key を解決できない場合は usage/configuration error とする

`--device-lock-timeout` は、既に取得されている lock を何秒待つかを制御する。
timeout 時の error message には、要求した key と、既存 lock file から読める診断 metadata を含めることが望ましい。

`--device-lock-dir` は既定の user runtime/cache lock directory を上書きする。
CI の分離や、共有 lab machine で明示的な調整が必要な場合に使う。

`--device-lock-key` は primary DUT の自動 key 解決を上書きする。
serial port 文字列が物理 device identity として安定しない特殊環境向けである。
peer DUT は、将来 peer 専用 override を追加するまでは、それぞれの解決済み port key を使う。

## 13. DUT / Serial 連携要件

### 13.1 基本方針

- DUT・serial・expect は `pytest-embedded` の既存 generic 機能を活用する
- `EspSerial` や ESP 向け専用クラスには依存しない

### 13.2 設計意図

- build / upload と test runtime を分離する
- テストランタイム側はできるだけ board 非依存で保つ
- 将来、必要に応じて board family ごとの差分を upload strategy または service 層へ切り出せるようにする

### 13.3 到達点

- generic serial で接続できる前提のボードでテスト可能
- `pytest-embedded` 標準 DUT を使った `expect` ベースの基本テストが成立する
- profile ごとに異なる serial port を環境変数から解決できる
- host machine 上で動作する board core では、pyserial の `socket://` URL を使って TCP/IP 経由で DUT に接続できる

### 13.4 host Arduino core の socket 接続

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

このファイルはリポジトリ間の契約である。host Arduino core が書き、この plugin が読む。ファイル名の形と `port` キーは変えない。キーは増えることがあり、plugin は知らないキーを無視する。

`socket://localhost:56789` のように port 番号まで指定された場合は、JSON 探索による補完を行わず、その URL をそのまま runtime 接続先として使う。

`--flash-port` が指定された場合は既存の port 優先順位に従い、upload 用 port として優先する。
host Arduino core の socket 実行では、通常 `--flash-port` は使わず `--port=socket://...` を使う運用を想定する。

upload の標準出力に `HOST_ARDUINO_PORT=...` が出る場合でも、plugin は stdout capture を必須にしない。
既存の upload 表示挙動を変えないため、port 解決は build 出力ディレクトリの `*.host-arduino.json` を優先する。

host 実行は純粋なロジックや serial protocol の簡易確認用であり、実機テストの代替ではない。
OS、gcc などの toolchain version、host core の `Serial` class 実装差により結果が変わる可能性がある。
peripheral、timing、割り込み、Flash/NVS、board 固有 API は実機で確認する。
また、本番で使う board profile での build test は別途行うことを推奨する。

### 13.5 skip の責務分担

本プラグインは、profile 非対応による skip を build 前に判定できるべきである。

- `sketch.yaml` に存在しない profile を指定された場合は、その sketch を compile / upload 前に skip する
- この skip は test 関数内の `pytest.skip()` に依存しない

同じ profile でも実機状態や外部条件によって適用対象外になる場合は理由付き skip を使える。収集時に判断できる条件は 24.10 の API で build 前に判定する。
実行時にしか分からない前提条件は Python 側で扱う。ただし、設定済みの Wi-Fi や外部サービスへの接続失敗が検証対象なら、失敗を skip に変えない。

### 13.6 peer DUT の profile 解決

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

### 13.7 peer DUT の port 解決

`--port` と `--flash-port` は primary DUT 専用とする。
peer DUT の port は peer 名に基づいて解決し、primary DUT の port 指定を暗黙に流用しない。

peer DUT の runtime port 解決順は次の通り。

1. `--peer-port <name>:<port>`
2. `TEST_SERIAL_PORT_PEER_<NAME>_<PROFILE>`
3. `TEST_SERIAL_PORT_PEER_<NAME>`
4. `peer_<name>/sketch.yaml` の `profiles.<profile>.port`
5. 解決できなければ、その peer DUT を必要とするテストを skip する

`<NAME>` と `<PROFILE>` は大文字化し、`-` を `_` に置換した形式とする。
例えば `peer_echo` の `host` profile では `TEST_SERIAL_PORT_PEER_ECHO_HOST` を参照する。
1 つのテストの 2 つの peer が同じ変数を読むことになる場合は設定エラーとする。例えば profile `c` の `peer_a_b` と profile `b_c` の `peer_a`（どちらも `TEST_SERIAL_PORT_PEER_A_B_C`）や、`peer_a-b` と `peer_a_b` である。

peer DUT の upload port 解決では、runtime port が `socket://...` URL の場合は `arduino-cli upload --port` へ渡さない。
これは primary DUT と同じく、socket URL を runtime 接続先として扱うためである。

peer DUT でも host Arduino core の port 番号なし socket URL を使える。
`socket://localhost` のような URL は、該当 peer DUT の upload 後に、その peer DUT の build 出力ディレクトリ配下の `*.host-arduino.json` から `port` を読み取って補完する。

### 13.8 peer DUT の build / upload / connect

peer DUT の build path は、各 peer sketch ディレクトリ配下の `<peer_dir>/build/<profile or default>` とする。
primary DUT の build path と peer DUT の build path は分離する。

peer directory が存在する場合、build が有効な実行では primary upload より前に peer DUT を compile する。
`peers` fixture が要求された場合、plugin は検出された peer DUT について upload / runtime port 補完 / 接続を行う。
`peers["<name>"]` は接続済み peer DUT を参照するための mapping API であり、参照された peer だけを遅延起動する仕様にはしない。

- `--run-mode=all`: peer DUT を build し、upload してから test を実行する
- `--run-mode=build`: peer DUT を build し、test 実行は skip する。この場合 peer port は不要
- `--run-mode=test`: 既存 build artifact を使って peer DUT を upload してから test を実行する

build / upload の順序は次の通りとする。

1. primary DUT を build する
2. 検出された peer DUT を名前順で build する
3. primary DUT を upload する

その後、function scope の `dut` と `peers` fixture は、テスト関数の引数に並べた順に用意される。plugin は両者の順を固定しない。

- `dut`: pytest-embedded の通常処理により primary DUT に接続する
- `peers`: 検出された peer DUT を名前順で upload し、runtime port を補完して接続し、`peers["<name>"]` として提供する

この順序では、実機 DUT が upload 直後に短時間だけ出力する起動メッセージを Python 側が取りこぼす可能性がある。
host Arduino core のように出力が socket 接続まで保持される環境では問題になりにくいが、一般の実機 serial では sketch 側で十分な待機、再送、または Python 側からの入力を待つ handshake を用意することを推奨する。
特に peer DUT では、`peers` fixture が要求された時点で検出済み peer をすべて起動するため、DUT 間の起動順に依存するテストは sketch 側 protocol で同期する。

peer DUT の構造不備は設定エラーとして扱う。
例えば `.ino` がない、`.ino` が複数ある、`sketch.yaml` が壊れている場合は error とする。
一方で、profile 非対応、profile 未決定、port 未解決のように実行条件が揃わない場合は skip とする。

### 13.9 platform の pluggable monitor を通した runtime 接続

platform によっては、runtime の console を素の serial port ではなく platform 自前の pluggable monitor で出す（例: monitor の設定で source を選ぶ debug probe）。そうした port を pyserial で開くと monitor を通らないため、その platform では runtime の port を `arduino-cli monitor` 経由で読む。

判定:

- 対象の sketch について `arduino-cli compile --show-properties --profile <profile>` を実行する。profile を使うので、profile が固定した版の platform を見る。
- port の protocol は、`/dev/ttyACM0` や `COM3` のような素の path なら `serial`、`<scheme>://...` の形で書いた port なら scheme とする。例えば platform の pluggable discovery が出す `wchlink://FBC18F0680B0` や `oep://<probe>/<slot>` である。
- `pluggable_monitor.pattern.<protocol>` があるか、`pluggable_monitor.required.<protocol>` が `builtin:` で始まらない tool を指すとき、その protocol について自前の monitor があるとみなす。`builtin:serial-monitor` は自前の monitor を持たない platform に arduino-cli が補う既定なので、数えない。
- platform がその scheme の monitor を持たない URL（`rfc2217://...` など）は pyserial に任せる。`socket://...`（host core）は判定せず、常に pyserial に任せる。
- 結果は session の間、板ごとに保持する。profile の `fqbn` と `platforms` が同じ sketch は 1 回の判定を共有する。profile のない sketch は sketch ごとに判定する。
- 切り替えは自動で、上書きする option は無い。テストは `dut` と `peers` をそのまま使う。別名の fixture も marker も無い。

接続:

- runtime の port を `arduinomonitor://<address>?...` の URL にする。この文字列は API ではない。address、protocol、profile が要るコードは `pytest_embedded_arduino_cli.MonitorTarget.from_url` で解く（21）。plugin はこの scheme の pyserial protocol handler を登録するので、`dut`、`peers`、`dut.write`、`expect`、ログは変わらず動く。
- handler は sketch directory を cwd にして `arduino-cli monitor -p <address> -l <protocol> --quiet -m <profile>` を起動し、stdin と stdout をパイプにする。どちらの向きもバイトは変わらず通る。stderr は data に混ぜない。
- stdin は session の間ずっと開いておく。stdin が EOF になると arduino-cli は session を終える。monitor が port を開く前に書いたバイトは、開いた後に届く。
- port の設定は arduino-cli に任せる。`boards.txt` の `monitor_port.serial.<id>` が板の既定で、`sketch.yaml` の profile の `port_config` がそれを上書きする。plugin はそのための option を持たず、`--baud` もこの接続には効かない。profile を使うとき、`sketch.yaml` の top-level の `default_port_config` は arduino-cli が適用しない。monitor が宣言しないキーを書くと、arduino-cli は session を開く前に止まる。
- close では stdin を閉じる。arduino-cli は monitor tool に `CLOSE` を送って終わる。数秒で終わらなければ terminate する。monitor tool は別の process group で動くので、stdin の EOF で終わる作りであることを前提とする。
- plugin が閉じていないのに stream が終わった場合、read は arduino-cli の exit code と stderr を添えた serial error を出し、ログに残す。再接続や monitor の起動し直しはしない。monitor が port を開けなかった場合は、arduino-cli の stderr に monitor のメッセージが出る。
- 開くのに約 1 秒かかり、arduino-cli は monitor tool を 2 回起動する（設定の列挙に 1 回、session に 1 回）。session が開く前に板が出した出力は受け取れない。これは upload の後に開くどの接続でも同じである。

`arduino_cli_build_properties` fixture（module scope）は、同じ `--show-properties` の結果を `dict[str, str]` で返す。sketch と profile ごとに 1 回だけ実行する。汎用の fixture で、他の plugin が対象の platform の `runtime.tools.<tool>.path` などを読むのに使える。`build_config.toml` から注入する値は含まない。

## 14. pytest option 要件

少なくとも次のカテゴリの option を対象とする。

### 14.1 実行モード

- build するか
- upload するか
- test を実行するか

例:

- `--run-mode=all|build|test`

意味は次の通り。

- `all`: build → upload → test
- `build`: build のみ
- `test`: 既存 build artifact を使って upload → test

### 14.2 Arduino CLI compile 関連

- profile

本プラグイン固有の compile 関連 option は `--profile` と `--clean` とする。

`--clean` は 2 つの役を持つ。`arduino-cli compile` に `--clean` を渡すことと、実行前に ArduTest の artifact directory を消すことである。どちらも 1 つの option のまま保つ。
build path は `<sketch_dir>/build/<profile or default>` に固定し、MVP では override を持たない。

build 実行前に profile 対応可否を判定し、非対応 profile の sketch では compile を行わない。

### 14.3 Arduino CLI upload 関連

本プラグイン固有の upload 関連 option は追加しない。
upload に必要な port 指定は `pytest-embedded` 標準の `--flash-port` または `--port` を使う。
ただし、`--port=socket://...` は runtime 接続先を表すため、`arduino-cli upload --port` には渡さない。

### 14.4 peer DUT 関連

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

### 14.5 serial / DUT 関連

- `pytest-embedded` 標準 option を活かす
- 必要に応じて plugin 側で橋渡しする
- 少なくとも `--port`、`--flash-port`、`--baud`、`--embedded-services` を前提とする

runtime の port は次の優先順で解決する。

1. `--port`
2. profile ごとの環境変数
3. 共通環境変数
4. `sketch.yaml` の `profiles.<profile>.port`

upload の port は、`--flash-port` があればそれ、なければ runtime の port とする。`socket://...` の runtime port は `arduino-cli upload --port` に渡さない。
`--flash-port` を runtime の port として使うことはない。

profile ごとの環境変数名は、例えば `TEST_SERIAL_PORT_ESP32S3` のように profile 名を正規化した形式とする。
共通環境変数は `TEST_SERIAL_PORT` とする。

`--port` または環境変数に `socket://localhost` のような socket URL が指定された場合は、runtime 接続先として扱う。
port 番号なしの socket URL は、upload 後に build 出力ディレクトリの `*.host-arduino.json` から `port` を読み取って補完する。
port 番号ありの socket URL は補完せず、そのまま使う。

platform が runtime の port の protocol（素の path なら `serial`、`wchlink://...` などなら scheme）について自前の pluggable monitor を持つときは、runtime の port を pyserial で開かず、`arduino-cli monitor` 経由で読む（13.9 を参照）。

### 14.6 Device Lock 関連

共有物理 DUT を複数 pytest process から保護するため、device lock option を追加する。

- `--device-lock=auto|off|required`
- `--device-lock-timeout=SECONDS`
- `--device-lock-dir=PATH`
- `--device-lock-key=KEY`

既定値は `auto` とする。
これにより、通常の実機 upload/test run は追加設定なしで保護され、build only や既定の socket based host run では物理 device lock の待機を行わない。

### 14.7 pytest 標準 verbosity 連携

- 追加の専用 verbose option は設けない
- pytest 標準の `-v` / `-vv` に従って build / upload のログ出力量を変える
- `-v` では `arduino-cli compile` / `arduino-cli upload` の実行コマンドを表示する
- `-vv` では上記に加えて `cwd`、`sketch_dir`、`build_path`、`profile`、`port` などの実行文脈も表示する

build 前 skip が発生した場合、`-v` 以上では非対応 profile により skip したことが分かる出力を持つことが望ましい。
peer DUT の build / upload でも、`-v` / `-vv` のログには peer 名が分かる情報を含める。

### 14.8 option 設計方針

- 命名は `arduino-cli` の用語を優先する
- ESP 固有用語を option 名に持ち込まない
- pytest-embedded 既存 option と競合しにくい名前にする
- build / upload / runtime の責務境界が option 名から見えるようにする
- plugin 固有 option は、実行 mode、profile 選択、peer DUT、device lock、ArduTest、local state cache、log directory summary の範囲に絞る
- `--port`、`--flash-port`、`--baud` は `pytest-embedded` の option である。plugin はこれらを読み、解決した runtime の port を現在の module の間だけ `--port` に書き戻すことがある
- `--arduino-cli-no-log-summary` のように接頭辞が揃っていない名前も、既存の option 名は変えない

### 14.9 log directory 結果 summary

log directory `<tmpdir>/pytest-embedded/<UTC timestamp>/<テスト名>/` は `pytest-embedded` が所有し、そこには serial log しか出力されない。
そのため directory tree から実行結果が分からないので、本 plugin は同じ directory に結果ファイルを追加する。

- 各テスト directory に status ファイルをちょうど 1 つ出力する: `PASSED.txt`、`FAILED.txt`、`ERROR.txt`、`SKIPPED.txt`、`XFAILED.txt`、`XPASSED.txt`
  - `ERROR.txt` は setup / teardown の失敗を表し、build や upload の失敗はここに現れる
  - status ファイルには test id、phase ごとの所要時間、profile、log ファイル名、失敗時はその内容を含める
  - 同じ directory に残っている前回実行の status ファイルは削除し、tree 上で結果が矛盾しないようにする
- session log directory の直下に、件数を名前に持つ 0 byte の marker を出力する（例: `FAILED-2_PASSED-7`）。`tree` や `ls` の 1 行で結果が分かることを目的とする
- 実行全体について、人が読む `SUMMARY.txt` と機械可読な `summary.json` を出力する
- 失敗内容は上限サイズで末尾を残して切り詰める。完全な serial log は同じ directory の `dut.log` とする
- `pytest-embedded` が log directory を作らなかった実行では何も出力しない。また本機能の失敗が pytest の exit status に影響してはならない
- option: `--arduino-cli-no-log-summary` で本機能を無効化する。既定値は有効

## 15. テスト状態保存要件

### 15.1 目的と位置付け

pytest で実行したマイコン向け実機テストについて、各テストの検証状態をローカルファイルに保存する。

主目的は、ローカル開発中に「最後にいつ成功したか」「前回の結果はどうだったか」を確認できるようにすることである。

本機能は「実機 verification state cache」として扱い、以下は対象外である。

- テストレポート、長期履歴管理、CIダッシュボード、品質ゲート
- 実行履歴の蓄積、メトリクス収集、trend 分析
- build artifact、ログ、シリアル出力、スクリーンショットなどの artifact 保存
- stale entry の自動削除や rename 検出

state cache は実行環境に応じてリセットしてもテスト本体やビルドに影響しない disposable なファイルである。

### 15.2 基本方針

- state は実機上で実際に verification が行われた場合のみ更新する
- 認識単位は `(profile_name, nodeid)` の組とする
- profile ごとに別ファイルへ分割することは初期仕様に含めない
- state.json は current state cache であり、append-only history は保持しない
- pytest collection との完全一致を保証しない
- stale entry が残ることを許容する

### 15.3 保存先と構成

#### 15.3.1 ディレクトリ設定

状態保存ディレクトリは CLI option で指定可能とする。

- option: `--save-state-dir`
- default: `.pytest-results`
- absolute path または relative path（pytest rootdir 基準）を指定可能
- git 管理外とすることを推奨し、`.gitignore` への追加を推奨する

#### 15.3.2 ファイル構成

- state は `<save_state_dir>/state.json` に保存する
- `<save_state_dir>/` はローカル状態保存用ディレクトリとして扱う
- 将来の拡張用に他のキャッシュファイルを置ける構造を想定するが、初期仕様では `state.json` のみ

#### 15.3.3 state.json 構造

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

### 15.4 保存内容

各テストについて、少なくとも以下を保存する。

- `last_result`: 最終結果（`passed`、`failed`、`error` など）
- `last_run_at`: 最終実行日時（ISO8601 形式、タイムゾーン付き）
- `last_success_at`: 最終成功日時（ISO8601 形式、タイムゾーン付き）

- 最初に成功するまでは `last_success_at` は存在しなくてよい
- 未実行テストは `state.json` に entry が存在しないことで表現する
- JSON は人間にも読みやすく、機械にも処理しやすい形式とする

### 15.5 保存対象の判定

state を更新するのは、実機上で実際に verification が行われた場合のみである。

次の場合は state を更新しない：

- `build failed`: compile に失敗した場合
- `upload failed`: upload に失敗した場合
- 環境要因による失敗: board not found、port open failed、device unavailable など
- `skipped`、`deselected`: テストが実行されなかった場合

state を更新する場合：

- `pass`/`fail`/`error` など、実際にボード上でテストが開始された結果のみ更新対象
- upload 成功後にテスト実行へ到達した場合のみ更新対象

### 15.6 結果更新動作

- 実行されたテストだけを upsert する
- 実行されなかったテストの entry は変更しない

成功時（`pass`）：
- `last_result`、`last_run_at`、`last_success_at` を更新する

失敗時（`fail`/`error` など）：
- `last_result`、`last_run_at` のみ更新し、既存の `last_success_at` は保持する

テストの削除、rename、対象外化によって古い entry が残ってもよい。
stale entry の cleanup は初期仕様に含めない。

### 15.7 peer DUT の扱い

peer DUT を使うテストでも、state cache には primary DUT（親ディレクトリの sketch）のみの結果を保存する。

- peer DUT の build / upload 状態は記録しない
- 単一実行の `nodeid` は peer 名を含まない。24 章の組合せ mode は peer profile を含めて構成を区別する
- 同じ `nodeid` を持つテストが複数台で実行されても、state には primary DUT の結果のみ反映される

### 15.8 ArduTest との独立性

state cache 機能は ArduTest に依存しない。

- ArduTest を使わないテストでも state cache を利用できる
- ArduTest fixture の有無にかかわらず、テスト実行がボード上で行われた結果が記録される
- `pytest-embedded` 標準の expect による basic テストでも state cache に entry が作成される

### 15.9 CLI option 追加

state cache 機能を制御するため、pytest option に次を追加する。

- `--save-state`: flag 形式。指定された場合のみ state を保存する（default: 無効）
- `--save-state-dir`: 値指定形式。state.json を保存するディレクトリを指定（default: `.pytest-results`）

例：

```bash
pytest tests/foo --save-state
pytest tests/foo --save-state --save-state-dir .test-cache
```

`--save-state-dir` が指定されても `--save-state` がない場合、state は保存されない。

### 15.10 実装上の考慮

#### 15.10.1 plugin 層の責務

- pytest hook（`pytest_runtest_logreport` など）を使ってテスト結果を捕捉
- build / upload 成功の確認（失敗時は state 更新をスキップ）
- テスト実行が実機上で行われたかどうかの判定
- profile 名の確定
- nodeid の取得
- state.json の読み書き（ファイル I/O）

#### 15.10.2 ファイル I/O 設計

- state.json が存在しないとき、初期構造を自動生成する
- `<save_state_dir>/` ディレクトリが存在しないとき、自動作成する
- 複数テストの同時実行（pytest-xdist など）による race condition は、初期仕様では対応外とする
- ユーザーが state.json を削除または手動編集してもテスト本体に影響しない

#### 15.10.3 テストの判定

テスト実行が実機上で行われたかの判定基準：

- upload フェーズが成功した後、test フェーズの execution に到達したこと
- item の upload 成功と call 到達を確認し、teardown report で最終結果を確定する。teardown 失敗時は error とし、その実行の成功時刻を更新しない

#### 15.10.4 profile 名の確定

- `--profile` が明示指定された場合はその値を使用
- 自動選択（`--profile` 未指定で profile 1 つの場合）された場合、選択された profile 名を使用

### 15.11 スコープ外

- state.json の content versioning や migration 機構は初期仕様に含めない
- stale entry の自動検出・削除は行わない
- history file や long-term metrics は初期仕様に含めない
- CI 向けレポート生成や HTML 表示は初期仕様に含めない
- `sketch path` や `fqbn` のような override option は必須要件に含めない
- ログ出力制御は pytest 標準の verbosity に従わせ、専用 option を増やさない

## 16. テスト要件

### 16.1 単体テスト

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
- device lock mode option の解釈と既定値 `auto`
- 物理 serial port からの device lock key 解決
- `socket://...` target を既定では lock しないこと
- compile 後、upload 前に lock を取得すること
- 複数 DUT lock の決定的な取得順
- OS lock が保持されていない stale lock file を許容すること
- log directory summary の status ファイル、root marker、`SUMMARY.txt`、`summary.json` の内容
- 前回実行が残した status ファイルと marker を置き換えること
- 複数の test id が同じ log directory 名を共有する場合に最も重い status を採用すること
- `--arduino-cli-no-log-summary` で log directory summary を無効化できること

### 16.2 最小統合テスト

少なくとも次を検証する。

- pytest plugin としてロードできること
- `pytest --help` または plugin manager 上で option が見えること
- fixture が解決できること

### 16.3 テスト方針

- 実機依存を避ける
- `subprocess.run` はモック可能な設計にする
- Arduino CLI 実行の成否よりも、まずは責務分離とインターフェース安定性を検証する
- verbosity 連携の検証では、標準出力そのものではなく plugin 内のログ分岐を確認してよい

## 17. examples 要件

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

## 18. README 要件

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
- device lock の挙動と既定値 `auto`
- `-v` / `-vv` 時のログ挙動
- 設計方針
- 今後の拡張候補

## 19. 非機能要件

### 19.1 保守性

- モジュール境界が明確であること
- subprocess 実行とコマンド生成が分離されていること
- board 固有処理を混在させないこと

### 19.2 拡張性

- 将来 service 層や strategy 層へ切り出しやすいこと
- upload 実装を board family ごとに差し替えやすいこと
- build property や artifact 解決ルールを追加しやすいこと

### 19.3 可搬性

- 少なくとも Linux / macOS を前提に不自然な前提を持たないこと
- シリアルポートや CLI パスの扱いで特定環境に強く依存しすぎないこと

## 20. 参考実装から取り込む観点

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

## 21. 公開 API

次の名前を plugin の公開 API とし、semantic versioning に従う。

- fixture
  - `arduino_cli_app`（module）: 解決済みの `ArduinoCliBuildConfig`
  - `arduino_cli_flasher`（module）: 解決済みの `ArduinoCliUploadConfig`
  - `arduino_cli_build_properties`（module）: 対象の sketch と profile の `arduino-cli compile --show-properties` の `dict[str, str]`（13.9）
  - `arduino_test`（function）: ArduTest の session（[`ARDUTEST_PYTEST_SPEC.ja.md`](ARDUTEST_PYTEST_SPEC.ja.md)）
  - `peers`（function）: peer 名から DUT への mapping（13.8）
- Python
  - `pytest_embedded_arduino_cli.MonitorTarget`: `MonitorTarget.from_url(port)` で `arduinomonitor://` の runtime port を解き、`to_url()` で作る。フィールドは `address`、`protocol`、`profile`、`sketch_dir`、`cli_path`
  - `pytest_embedded_arduino_cli.is_monitor_url(port)`
- option（14 章）と環境変数（14.5、13.7）
- `ArduinoCombination`、`arduino_skip_if` marker、`pytest_arduino_cli_skip_reason` hook（24.10）
- `*.host-arduino.json`（13.4）

`arduinomonitor://` の URL の文字列そのものは API に含めない。runtime の port の裏の address や profile が要るコードは、文字列を切り出さず `MonitorTarget.from_url` で解く。

`app.py`、`flasher.py`、`serial.py`、`plugin.py` の補助関数を含むその他のモジュールと関数は内部のもので、どのリリースでも変わりうる。

## 22. 受け入れ条件

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
12. device lock は物理 serial upload/test run に対して既定で `auto` mode として有効である
13. device lock は compile 後 upload 前に待機し、DUT 利用終了まで保持される
14. `--device-lock=off` で device lock を無効化できる
15. `--save-state` option で state cache 保存の有効/無効を制御できる
16. `--save-state-dir` option で state.json の保存先を指定できる
17. state.json に `(profile_name, nodeid)` 単位でテスト状態が記録される
18. 実機上で実行されたテストのみ state.json に entry が作成される
19. peer DUT の state は記録されず、primary DUT のみ記録される
20. ArduTest に依存せず、基本的な pytest-embedded テストでも state cache が機能する

## 23. 今後の拡張候補

- board family ごとの upload strategy 差し替え
- `arduino-cli board list` 連携によるポート解決支援
- artifact 自動探索と board ごとの差分吸収
- monitor / reset 制御の抽象化
- build profile と test matrix の統合
- `fqbn` override や sketch path override の追加
- board core / fqbn ごとの capability 宣言

複数 profile と peer の組合せ実行については、次章に仕様を定める。

## 24. 明示指定による複数 profile / peer 組合せ実行

### 24.1 状態と目的

本章の機能は次期リリース向けに実装済みである。
従来実装 `a50b0de8b47a` の単一 profile 実行を維持したまま、明示指定した場合だけ複数の実行構成を一度の pytest session 内に展開する。
6、13、14、15 章の単一構成の規則に対し、組合せ mode の差分は本章を適用する。収集時の適用条件判定は単一実行と通常の Python テストでも利用できる。

- plugin は候補の展開、構成ごとの DUT lifecycle、skip 判定、結果の識別を担当する。
- 利用側は profile 定義、役割別の実機割当、機能・配線の適用条件を担当する。
- CI の job 分割と job 間の artifact 集計は外側の責務とする。
- 設備の自動発見、配線の自動切替、device farm、実機並列化は追加しない。
- 独自の matrix 設定ファイルや `sketch.yaml` の独自項目は追加しない。

### 24.2 CLI と候補の選択

追加する option は次のとおりとする。

| option | 意味 |
|---|---|
| `--profiles=all` | 各 primary sketch に定義された全 profile を候補にする |
| `--profiles=esp32,esp32s3` | primary の候補を指定した名前に限定する。1 個の指定も許す |
| `--peer-profiles=all` | 使用する各 peer sketch の全 profile を候補にする |
| `--peer-profiles=echo:esp32,esp32s3` | 名前付き peer の候補を指定した名前に限定する |
| `--peer-profiles=echo:all` | 名前付き peer だけ全 profile を候補にする |

名前付き `--peer-profiles` は異なる peer に対して繰り返し指定できる。指定しなかった peer は従来の解決規則を使う。
裸の `--peer-profiles=all` は全 peer を対象とする特別な指定であり、名前付き指定や既存の `--peer-profile` とは併用しない。
`--profiles` と既存の `--profile`、同じ peer に対する `--peer-profiles` と既存の `--peer-profile` は競合として error にする。
異なる peer については、名前付き複数指定と既存の単一指定を併用できる。

| primary の選択 | peer の選択 | 実行対象 |
|---|---|---|
| 新 option なし | 新 option なし | 従来の単一構成 |
| `all` | 指定なし | primary 全候補 × peer の default / 既存明示指定 |
| 指定なし | `all` | primary の default / 既存明示指定 × peer 全候補 |
| `all` | `all` | 両側の全候補の直積 |
| 明示した候補 | 明示した候補 | 指定した候補同士の直積だけ |

無指定時は primary の `--profile` → `default_profile` → 単一 profile fallback、peer の `--peer-profile` → `default_profile` を維持する。
default がないことを理由に全候補へ展開しない。peer では単一 profile の自動選択を追加しない。
primary だけに `all` を指定しても peer 全候補には広げない。
peer が複数なら、各 peer の候補をそれぞれ軸として直積を生成する。
`all` は新 option の予約値とし、同名 profile の単一選択には既存の `--profile all` / `--peer-profile <name>:all` を使える。

新 option のいずれかを指定した実行を、本章では「組合せ実行モード」と呼ぶ。候補が 1 個でもこの mode の事前確認を適用する。

### 24.3 収集と入力検証

実行構成は primary profile と、名前順に並べた使用 peer の profile mapping で識別する。
profile の列挙は既存の sketch 解決規則を使い、各 sketch に対して解決された `sketch.yaml` を読む。環境変数や機材の有無によって収集 item を黙って除外しない。

- `all` は各 sketch の定義内だけを列挙する。全 sketch の profile の和集合を全 sketch に掛け合わせない。
- 明示候補が個別 sketch で非対応なら、構成と理由の分かる skip item を残す。
- 明示した profile 名が対象のどの sketch にも存在しない場合は、入力ミスとして error にする。primary と名前付き peer は別々に検証する。
- 空の list、候補の重複、同じ peer への重複指定、未知の peer 名、`all` と名前の混在、壊れた設定は error にする。
- `all` の列挙対象に profile がない場合や、選択した Arduino 対象で構造上有効な構成が一つもない場合は error にする。port 未設定で全件 skip になる場合とは区別する。
- `.ino` のない通常の Python テストは profile 数だけ増やさない。
- 裸の `--peer-profiles=all` は peer のない module に peer 軸を追加しない。名前付き指定の未知 peer 判定は、収集対象全体で該当 peer が存在するかで行う。
- `peers` fixture を要求しないテストは peer の組合せ数だけ増やさず、peer の port 不足でも skip しない。間接的な fixture 依存も考慮する。
- 同じ module に peer 使用・不使用のテストが混在する場合も、必要な構成だけを生成し、同じ primary の peer 不使用テストを重複実行しない。
- ID と候補の順序は決定的にし、既存の test parameter と組み合わせても衝突しない。

ID は `primary=<profile>,<peer>=<profile>,...` とし、peer 名を辞書順に並べる。名前に含まれる区切り文字は percent encoding し、未解決 profile は `<unresolved>` で表す。既存の parameter ID と併用できる。表示例は次のとおり。

```text
test_link[primary=esp32,echo=esp32]
test_link[primary=esp32,echo=esp32s3]
test_link[primary=esp32s3,echo=esp32]
test_link[primary=esp32s3,echo=esp32s3]
```

`--collect-only` では予定 item の列挙と静的な設定検証だけを行う。機材への接続、外部設備への plan 要求、build、upload、monitor 起動、device lock 取得を行わない。
`--clean` が併用されても、収集のみでは既存 artifact を削除しない。

### 24.4 port 解決と実行前の skip

組合せ実行モードでは、構成に必要な primary / peer の接続先を、最初の DUT 書込みより前に確認する。
設定だけで判定できる不足は compile より前に skip し、不要な build を避ける。

| 条件 | 組合せ実行モードの動作 |
|---|---|
| 必要な primary / peer の runtime port が未解決 | 構成と不足した役割を示して skip |
| 同じ構成内の異なる役割が同じ物理 DUT を使用 | 衝突した役割を示して skip |
| 設定済み port の接続失敗、compile / upload 失敗 | error。未設定 skip に置き換えない |
| lock の取得失敗 / timeout | error。port 未設定として扱わない |
| `--run-mode=build` | port と実機重複による skip を適用せず compile する |
| host core | socket 設定が解決できれば対象にする。物理 serial port を要求しない |

判定は「環境変数がない」ではなく「接続先を解決できない」で行う。profile 固有の環境変数と `profiles.<profile>.port` は引き続き利用できる。
複数候補を持つ役割に対しては、profile を区別しない共通 port を異なる chip へ自動流用しない。
その役割の共通 CLI port 指定（primary の `--port` / `--flash-port`、peer の `--peer-port`）を error とし、共通環境変数 fallback を適用しない。
候補が 1 個の役割には従来の port 解決順を適用する。新 option のない従来実行の port 解決と error / skip 動作は変更しない。
この制限は profile 固有の設定に同じ port を明示することを禁止するものではなく、別々の構成が同じ DUT を逐次使用することは許す。

重複判定は port 文字列の一致だけに頼らず、symlink 解決など既存の device lock と整合する物理識別を使う。
primary と peer 間だけでなく peer 同士も確認する。別の upload / runtime port が分かっている場合は、その対応も考慮する。
任意の異なる port 表記が同じ実機かを自動発見する機能は含めず、利用側が正しい割当を提供する。
host の `socket://localhost` のような動的 port の placeholder が同じであるだけでは、物理 DUT 重複として skip しない。
upload 先と runtime 接続先の区別、および socket URL を upload port に渡さない既存仕様を維持する。

新しい skip 専用 option は必須としない。新しい組合せ実行モードの動作として上記を提供する。
配線・能力等の外部設備の判定は利用側で行い、必要なら最初の upload より前の事前確認へ組み込む。OEP 等の固有 API は plugin に持ち込まない。

### 24.5 4 台 / 3 台の運用例

primary sketch と `peer_echo` の両方に `esp32`、`esp32s3` が定義されているものとする。
ESP32 が 2 台、S3 が 2 台ある場合の役割別環境変数は次のとおり。値は実環境の port とする。

| 環境変数 | 割当 |
|---|---|
| `TEST_SERIAL_PORT_ESP32` | primary 用 ESP32 |
| `TEST_SERIAL_PORT_ESP32S3` | primary 用 S3 |
| `TEST_SERIAL_PORT_PEER_ECHO_ESP32` | peer 用 ESP32 |
| `TEST_SERIAL_PORT_PEER_ECHO_ESP32S3` | peer 用 S3 |

```bash
# 1 テストにつき 4 組を収集し、4 組を実行
pytest tests/link --profiles=all --peer-profiles=all

# peer を ESP32 に限定し、1 テストにつき 2 組を収集
pytest tests/link --profiles=esp32,esp32s3 --peer-profiles=echo:esp32
```

ESP32 が 2 台、S3 が 1 台なら、S3 は primary に割り当て、peer 用 S3 の port を未設定にする。
peer の S3 profile にも port の設定がない前提で、最初の command は 4 組を収集し、2 組を実行、peer が S3 の 2 組を skip する。
2 番目の command は最初から 2 組だけを収集する。
profile 候補から外すことと、予定に含めたうえで設備不足を skip として記録することを区別する。

### 24.6 fixture と資源の lifecycle

profile option を session 全体の config に順次上書きする実装や、test 本文内の loop は採用しない。
module scope の実行構成 parameter を導入し、app、build property、build / upload、monitor、port、peer、lock の lifecycle を依存させる。
同じ module / 構成のテストは可能な範囲でまとめ、構成変更時には前構成の依存 fixture を teardown してから次を準備する。

- module オブジェクトに残る peer の compile 済み / upload 済み cache は、構成ごとの状態へ移すか確実に破棄する。
- 解決済みの runtime port や monitor URL を、次の構成の入力として再利用しない。pytest-embedded への橋渡しも構成の寿命に閉じる。
- 必要な事前確認を終え、compile を完了した後、最初の upload 前に必要な物理 device lock を決定的な順序で取得する。
- DUT 接続と利用側 cleanup が終わるまで lock を保持し、途中の setup 失敗でも取得済み資源を解放する。
- cleanup の一つが失敗しても他の資源の解放を試み、teardown error を該当構成に記録する。共有資源を安全に解放できない場合、次の構成へ無条件に進まない。
- port 重複による構成不成立の判定と、他 process との device lock 排他は別々に維持する。
- 逐次実行を前提とし、xdist / 実機並列実行の対応は別案件とする。

`--run-mode=all` / `build` / `test` の役割は維持する。build-only の成功は既存どおり compile 成功と test 本文の skip で表し、実機検証の成功には数えない。
build path は各 sketch / profile の既存分離を基本とする。初期実装では plugin 独自の compile 省略 cache を追加せず、Arduino CLI の通常の差分 build を利用する。
将来 compile を省略する場合は、profile 名だけでなく source、core / library、build property / define 等の実際の入力を検証する。

### 24.7 結果、artifact、state cache

実行構成は setup 開始前から item と各 phase の report に結び付ける。
現在の config の「最後に使った profile」から結果の所属を推測しない。

- nodeid に構成を含め、setup error、skip、call の成否、teardown error を同じ構成へ帰属させる。
- serial log、ArduTest artifact、JUnit、summary で構成を識別できるようにする。異なる module / parameter / peer 構成の同名成果物を上書きしない。
- JUnit と既存 summary を基本とし、独自の大規模な report framework は追加しない。
- 選択済みの予定 item と完了結果を区別する。中断や `--maxfail` で未実行の item を passed / skipped として作らない。収集のみは実行結果として扱わない。
- 設備不足で全件 skip でも「全構成を検証済み」と表示しない。pytest 標準の exit code を維持し、必須構成の実行を要求する CI の判定は利用側に残す。
- `--save-state` は引き続き実際に test 本文へ到達した検証結果だけを更新し、未実行、skip、build / upload 失敗で過去の結果を更新しない。
- state の primary profile ごとの構造は維持し、組合せ mode では peer profile を含む nodeid によって結果を区別する。peer 単体の検証履歴を追加する意味ではない。
- 新 option のない単一実行の nodeid と state key は変更しない。単一実行と組合せ実行の記録を暗黙に同一視・統合しない。

### 24.8 改修範囲と外部 runner との関係

主な改修対象は `plugin.py` の option / collection / fixture / report、`app.py` の候補解決、`serial.py` / `device_lock.py` の接続先解決と重複確認、`log_summary.py` と ArduTest の artifact 保存先である。
state cache の保存対象と key の整合、pytest-embedded の fixture / log directory との互換も確認する。

外部 runner で既存の単一 profile pytest を subprocess 起動する案は、移行手段として残す。
その場合は構成別の JUnit、artifact、cache と、起動予定 / 終了状態 / 中断 / 未起動を記録する manifest を分離し、結果を束ねる。
既存 plugin の primary port 未設定は skip にならないため、runner が起動を見送る場合は pytest の skip と区別して記録する。
本改修では runner を実装せず、日常的な一覧・選択・部分再実行を一度の pytest session で扱える plugin 内展開を採用方針とする。

### 24.9 段階的な実装と受け入れ条件

1. 実行構成の内部表現を primary + peer mapping として設計し、まず peer なしの list / `all`、item ID、fixture 切替、結果分離を実装する。
2. 同じ構成モデルへ peer 候補の直積、port 未解決 / 実機重複の事前 skip、peer lifecycle を追加する。
3. artifact / summary / state と既存 parameter、選択・再実行の互換を確認し、仕様の既存章と日英ガイドを更新する。

少なくとも次を検証する。compile / upload / 接続は mock で検証できるようにし、実機 smoke test は別に行う。

- 新 option なしの default、単一 profile、peer default / 明示指定、従来の error / skip の回帰がない。
- peer なしで 2 profile × 2 テストを収集でき、片方の build 失敗を正しく帰属させ、他方を独立して実行できる。
- 両側 `all` の 4 台例が 4 構成になり、3 台例が 2 実行 / 2 skip、peer 明示限定が 2 構成になる。
- 複数 peer の直積と peer 同士の物理重複、間接的な `peers` 依存、peer 使用・不使用の混在を扱える。
- 未設定 port、非対応 profile、利用側の設備不足の判定が最初の書込み前に働き、必要な skip 理由が残る。
- 同じ device の別 symlink 表記を検出し、異なる構成間の同じ device の逐次利用や host の動的 socket を誤って skip しない。
- build-only は port なしで動作し、`collect-only` は機材操作・compile・artifact 削除を行わない。
- setup / teardown 失敗、構成変更後の接続先と firmware、lock 解放、peer cache の分離を確認する。
- 完全な nodeid 指定、`-k`、同じ候補指定での `--lf`、既存の `parametrize` との併用で構成 ID が安定する。
- `.ino` のない unit を複製せず、ログ / ArduTest artifact / JUnit / state の peer 違いの結果が衝突しない。
- 中断・`--maxfail`・全件 skip を実行完了や全件成功と取り違えない。

### 24.10 収集時の適用条件 API

通常は profile 候補で実行範囲を選び、候補の直積では表現できない特殊な制約だけを適用条件で除外する。
配線によりクロスできない組等を利用側が宣言できるよう、次の API を公開する。設備の意味や配線表は plugin に持たせない。

- `ArduinoCombination`: 読み取り専用の `primary: str | None` と `peers: Mapping[str, str | None]`。`pytest_embedded_arduino_cli` から import できる。
- `pytest.mark.arduino_skip_if(predicate, reason="...")`: `predicate(item, combination)` が `True` なら skip。実際の `bool` と空でない reason を必須とし、module / class / function / parameter に宣言できる。
- `pytest_arduino_cli_skip_reason(item, combination)`: `conftest.py` または plugin に置く hookspec。空でない理由の `str` か `None` を返す。hook wrapper は非対応。

両 API は `-k` / `-m` / `--lf` 等による選択後の収集 item に適用する。`item` から test 名、nodeid、path、marker、pytest config を参照できる。
Arduino sketch のない item の `combination` は `None`、peer 不使用では `peers` が空であり、未解決の profile 値は `None` とする。
新しい profile option のない実行にも適用し、単一実行の nodeid を変えない。

hook は各 item のディレクトリに適用される実装だけを呼ぶ。兄弟ディレクトリの `conftest.py` を混ぜない。
上位・下位の hook とすべての marker は加算し、一つでも除外を求めれば標準の skip marker を付ける。`False` / `None` は他の制限を解除しない。
理由には marker の適用 node と判定関数の出典、または hook の出典を含める。
複数の条件があればすべて評価する。先に skip が決まっていても、例外・不正な戻り値・判定内の `pytest.skip()` 等は設定エラーとして実行を止め、build は始めない。
条件は静的な設定だけを読み、機材通信・fixture 取得・config 変更を行わない。`--collect-only` でも評価し、適用条件による skip と理由を表示する。port の実行前確認は収集時には行わない。

module fixture の setup より前に skip を判定し、対象外 item のためだけに compile / upload しない。ただし同じ firmware を別の実行対象が必要とする場合、その対象の build は行う。
ガイドでは候補選択、適用対象外、設備不足、失敗、中断を区別する。skip を検証成功や実行範囲の充足とみなさず、既知の不具合を除外で隠す運用を勧めない。
例は [テストの応用](TESTING_ADVANCED.ja.md#profile-の組合せと適用条件) に記載する。

以上を本プロジェクトの仕様とする。
