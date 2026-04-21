# pytest-embedded-arduino-cli 仕様書

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

## 6. 想定ユースケース

### 6.1 基本ユースケース

利用者は pytest 実行時に次を行えること。

1. Arduino sketch を `arduino-cli compile` でビルドする
2. ビルド成果物を `arduino-cli upload` で書き込む
3. シリアルポート経由で DUT に接続する
4. `dut.expect(...)` など `pytest-embedded` の標準的なインターフェースでテストする

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
- `build_config.toml` に基づく compile-time define 注入
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

### 10.4 `build_config.toml`

必要に応じて sketch ディレクトリに `build_config.toml` を置けるものとする。

想定用途:

- Wi-Fi SSID / password
- API endpoint
- テスト用フラグ

このファイルは、環境変数名と compile-time define 名の対応を定義するために使う。

想定例:

```toml
[defines]
TEST_WIFI_SSID = "WIFI_SSID"
TEST_WIFI_PASSWORD = "WIFI_PASSWORD"
```

plugin は指定された環境変数を読み、`arduino-cli compile --build-property build.extra_flags=...` に変換して渡す。
環境変数が未設定でも、その define には空文字を渡す。

`.env` ファイルの自動読込は本仕様には含めない。

### 10.5 コマンド生成方針

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

### 13.3 Arduino CLI upload 関連

本プラグイン固有の upload 関連 option は追加しない。
upload に必要な port 指定は `pytest-embedded` 標準の `--flash-port` または `--port` を使う。

### 13.4 serial / DUT 関連

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

### 13.5 pytest 標準 verbosity 連携

- 追加の専用 verbose option は設けない
- pytest 標準の `-v` / `-vv` に従って build / upload のログ出力量を変える
- `-v` では `arduino-cli compile` / `arduino-cli upload` の実行コマンドを表示する
- `-vv` では上記に加えて `cwd`、`sketch_dir`、`build_path`、`profile`、`port` などの実行文脈も表示する

### 13.6 option 設計方針

- 命名は `arduino-cli` の用語を優先する
- ESP 固有用語を option 名に持ち込まない
- pytest-embedded 既存 option と競合しにくい名前にする
- build / upload / runtime の責務境界が option 名から見えるようにする
- plugin 固有 option は `--run-mode` と `--profile` に絞る
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
- profile ごとの serial port 解決

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

## 20. 受け入れ条件

本仕様の受け入れ条件は次の通り。

1. `pytest-embedded-arduino-cli` が Python パッケージとしてインストール可能である
2. pytest plugin として自動ロードまたは明示ロードできる
3. `arduino-cli compile` を呼ぶ build 層が存在する
4. `arduino-cli upload` を呼ぶ flasher 層が存在する
5. `pytest-embedded` ベースで DUT / serial / expect を利用する基本設計になっている
6. ESP 固有依存が入っていない
7. 最低限の単体テストと plugin 読み込みテストが存在する
8. README と examples が存在する

## 21. 今後の拡張候補

- board family ごとの upload strategy 差し替え
- `arduino-cli board list` 連携によるポート解決支援
- artifact 自動探索と board ごとの差分吸収
- monitor / reset 制御の抽象化
- 複数 DUT 対応
- build profile と test matrix の統合
- `fqbn` override や sketch path override の追加
- board core / fqbn ごとの capability 宣言

以上を本プロジェクトの仕様とする。
