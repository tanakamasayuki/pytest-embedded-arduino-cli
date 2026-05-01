# ArduTest 通信プロトコル仕様（ドラフト）

## 1. 概要

本仕様は、Arduino 側ライブラリ `ArduTest` と `pytest-embedded-arduino-cli` 側 fixture `arduino_test` が、`Stream` 互換の通信路を通じて実機テストを制御するための通信プロトコルを定義する。

本仕様は以下を目的とする。

- 初期同期でテスト一覧、requirement、必須 config を取得できること
- `arduino_test` 側が実行計画を決定し、Arduino 側へ単一テスト実行を指示できること
- ログ、メトリクス、成果物、assertion 失敗、最終結果を機械的に収集できること
- Arduino Uno でも実装できる単純な形式に保つこと

本仕様はドラフトであり、既存の仮実装とは一致しない場合がある。実装は本仕様を優先して更新する。

---

## 2. 設計方針

### 2.1 基本方針

- 通信路は Arduino `Stream` を前提とする
- 1 行 1 メッセージのテキストプロトコルを基本とする
- 大きな本文や改行を含む本文は length-prefixed payload として扱う
- Arduino 側の受信バッファを小さく保つ
- pytest 側は厳密にパースし、不正な入力を明確なエラーにする
- 人間が serial monitor で読める程度の可読性を残す

### 2.2 非目的

- 高速なバイナリ RPC
- 任意 JSON オブジェクトの送受信
- Arduino 側での複雑な capability 判定
- pytest 以外の汎用クライアント互換性

---

## 3. 用語

- host: pytest を実行する PC
- device: ArduTest が動作する Arduino ボード
- command: host から device へ送る制御メッセージ
- event: device から host へ送る通知メッセージ
- payload: メッセージ末尾に続く任意長データ
- protocol version: ArduTest 通信仕様の互換性を表すバージョン

---

## 4. 通信形式

### 4.1 行形式

通常メッセージは ASCII 互換の 1 行テキストとする。

```text
AT <direction> <type> [fields...]\n
```

- `AT` は ArduTest プロトコルの固定 prefix
- `<direction>` は host から device が `>`、device から host が `<`
- `<type>` は大文字の message type
- `fields` は空白区切り
- 改行は `\n` を基本とし、受信側は `\r\n` も許容する

例:

```text
AT > HELLO 1
AT < HELLO 1 ArduTest 0.1.0
```

### 4.2 field encoding

`fields` は以下の制約を持つ。

- ASCII printable のうち空白を含まない文字列
- テスト名、requirement 名、config 名、metric 名は `[A-Za-z0-9_.:-]+` を推奨する
- 空白、改行、任意テキストを含む値は payload として送る

### 4.3 payload 形式

改行や空白を含む本文は header 行に byte length を含め、その直後に payload を送る。

```text
AT < LOG <test-name> <length>\n
<payload bytes>
```

payload の後ろに追加の終端文字は付けない。必要な場合、送信側は payload の直後に次の `AT ...\n` を続けてよい。

受信側は header の `<length>` byte だけを payload として読む。payload は初期コアでは UTF-8 テキストを想定する。

### 4.4 数値

- 整数は 10 進表記
- 浮動小数点数は `Stream.print(value, digits)` 相当の 10 進表記
- pytest 側は整数または float として解釈できない metric 値を protocol error にする

---

## 5. バージョンと互換性

### 5.1 protocol version

初期 protocol version は `1` とする。

host は接続後に対応 protocol version を送る。

```text
AT > HELLO 1
```

device は利用する protocol version、ライブラリ名、ライブラリ version を返す。

```text
AT < HELLO 1 ArduTest 0.1.0
```

host が対応しない protocol version を受け取った場合、テストを中止する。

### 5.2 ライブラリ version

ライブラリ version は Arduino ライブラリの release version を表す。protocol version とは独立して扱う。

---

## 6. 全体フロー

### 6.1 標準フロー

```text
1. pytest が arduino-cli compile / upload を実行する
2. pytest が serial 接続を開く
3. pytest が必要なら reset / 起動待ちを行う
4. host -> device: HELLO
5. host -> device: LIST
6. device -> host: TEST / REQUIRE / REQUIRE_CONFIG / END_LIST
7. pytest が capability と config を評価する
8. host -> device: SET_CONFIG
9. host -> device: RUN
10. device -> host: RUNNING / LOG / METRIC / ARTIFACT_TEXT / FAIL / RESULT
11. pytest が pytest result、log、artifact、metric に反映する
```

### 6.2 skip の扱い

skip は原則として host 側で決定する。

- requirement が満たされない場合、host は該当テストへ `RUN` を送らず pytest 上で skipped とする
- 必須 config が不足する場合も host 側で skipped または error として扱う
- device 側は初期コアでは `SKIP` result を送らない

### 6.3 timeout の扱い

timeout は host 側責務とする。

- device は test timeout を自律判定しない
- host は `RUNNING` 受信から `RESULT` 受信までの時間を監視する
- timeout 時、host は pytest 上で error とし、必要なら reset する

---

## 7. host から device への command

### 7.1 HELLO

protocol version を確認する。

```text
AT > HELLO <protocol-version>
```

### 7.2 LIST

テスト一覧と metadata の送信を要求する。

```text
AT > LIST
```

device は `TEST`、`REQUIRE`、`REQUIRE_CONFIG` を送った後、`END_LIST` を送る。

### 7.3 SET_CONFIG

config 値を device に渡す。

```text
AT > SET_CONFIG <name> <length>\n
<payload bytes>
```

- `<name>` は config 名
- payload は config 値
- 同じ `<name>` が複数回送られた場合は後勝ちとする

### 7.4 CLEAR_CONFIG

device 側に保持された config を消去する。

```text
AT > CLEAR_CONFIG
```

reset なしで複数回実行する場合の状態汚染を避けるために使う。

### 7.5 RUN

単一テストを実行する。

```text
AT > RUN <test-name>
```

device は指定されたテストだけを実行し、最後に必ず `RESULT` を送る。

### 7.6 RUN_ALL

登録順に全テストを実行する。

```text
AT > RUN_ALL
```

`RUN_ALL` は手動確認や smoke test 用の補助 command とする。pytest の通常運用では host が `LIST` 後に実行計画を作り、`RUN` を繰り返す。

### 7.7 RESET_STATE

ArduTest の実行状態を初期化する。

```text
AT > RESET_STATE
```

config を保持するか破棄するかは未決事項とする。初期案では config は保持し、破棄が必要な場合は `CLEAR_CONFIG` を使う。

---

## 8. device から host への event

### 8.1 HELLO

device の protocol version と library version を返す。

```text
AT < HELLO <protocol-version> ArduTest <library-version>
```

### 8.2 READY

device が command 受付可能になったことを通知する。

```text
AT < READY
```

`READY` は起動時に自発的に送ってもよい。host は `READY` を待たずに `HELLO` を送ってもよいが、接続直後の起動待ちでは `READY` を利用できる。

### 8.3 TEST

登録済みテストを通知する。

```text
AT < TEST <test-name>
```

### 8.4 REQUIRE

テストの capability requirement を通知する。

```text
AT < REQUIRE <test-name> <requirement-name>
```

### 8.5 REQUIRE_CONFIG

テストの必須 config を通知する。

```text
AT < REQUIRE_CONFIG <test-name> <config-name>
```

### 8.6 END_LIST

テスト一覧送信の終了を通知する。

```text
AT < END_LIST
```

### 8.7 RUNNING

テスト開始を通知する。

```text
AT < RUNNING <test-name>
```

### 8.8 LOG

ログを通知する。

```text
AT < LOG <test-name> <length>\n
<payload bytes>
```

test 実行中ではないログは `<test-name>` を `-` とする。

### 8.9 METRIC

数値 metric を通知する。

```text
AT < METRIC <test-name> <metric-name> <value>
```

### 8.10 ARTIFACT_TEXT

テキスト成果物を通知する。

```text
AT < ARTIFACT_TEXT <test-name> <filename> <content-type> <length>\n
<payload bytes>
```

- `<filename>` は相対パス
- `<content-type>` は初期コアでは `text/plain` を基本とする
- host は path traversal を拒否する

### 8.11 ARTIFACT_BINARY

バイナリ成果物を通知する。

```text
AT < ARTIFACT_BINARY <test-name> <filename> <content-type> <length>\n
<payload bytes>
```

`ARTIFACT_BINARY` は拡張機能とし、初期コアでは必須にしない。

### 8.12 FAIL

assertion 失敗を通知する。

```text
AT < FAIL <test-name> <file> <line> <length>\n
<payload bytes>
```

payload には失敗した式、比較内容、補足メッセージのいずれかを含める。

### 8.13 RESULT

テストの最終結果を通知する。

```text
AT < RESULT <test-name> <status>
```

`<status>` は以下のいずれかとする。

- `passed`
- `failed`
- `error`

`skipped` は初期コアでは host 側 result とし、device は送らない。

### 8.14 ERROR

protocol error または実行不能な状態を通知する。

```text
AT < ERROR <code> <length>\n
<payload bytes>
```

代表的な `<code>`:

- `unknown_command`
- `unknown_test`
- `invalid_state`
- `invalid_config`
- `duplicate_test`
- `internal_error`

---

## 9. テスト metadata の登録モデル

### 9.1 要件

host が実行前に skip 判定できるように、device は `LIST` 応答で各テストの requirement と必須 config を送れる必要がある。

### 9.2 初期 API 案

テスト関数の中で `REQUIRE()` を呼ぶ方式では、実行前 metadata として取得できない。そのため、以下のいずれかを採用する。

案 A:

```cpp
TEST_CASE(test_wifi) {
  ASSERT_TRUE(true);
}

ARDUTEST_REQUIRE(test_wifi, "network");
ARDUTEST_REQUIRE_CONFIG(test_wifi, "ssid");
```

案 B:

```cpp
TEST_CASE_WITH_REQUIREMENTS(test_wifi, "network", "ssid") {
  ASSERT_TRUE(true);
}
```

初期案では、実装の単純さと C++ macro の扱いやすさから案 A を優先候補とする。

### 9.3 実行中 requirement

実行中に環境不足が判明するケースは assertion failure ではなく `error` とするか、将来の明示的 skip API で扱う。初期コアでは実行前 metadata に寄せる。

---

## 10. config モデル

### 10.1 提供元

host は以下から config を収集して device へ送る。

- pytest option
- pytest ini
- 環境変数
- ユーザー指定の設定ファイル

具体的な優先順位は `pytest-embedded-arduino-cli` 側仕様で定義する。

### 10.2 device 側保持

初期コアでは、device 側 config は小さな固定上限を持つ key/value store とする。

推奨初期値:

- 最大件数: 4
- key 最大長: 31 bytes
- value 最大長: 48 bytes

これらは ArduTest Arduino ライブラリの既定 compile-time define と一致する。
必要に応じて Arduino 側で上限を変更できるが、小容量ボードでは RAM 使用量に注意する。

上限を超えた場合、device は `ERROR invalid_config` を返す。

### 10.3 必須 config 不足

`REQUIRE_CONFIG` で宣言された config が host に存在しない場合、host は原則として該当テストを skipped にする。ただし利用者設定で error にできる余地を残す。

---

## 11. capability モデル

### 11.1 requirement 名

requirement 名は Arduino 側が任意文字列として宣言する。意味解釈は host 側が行う。

例:

```text
network
wifi
measurement.current
sensor.temperature
```

### 11.2 capability 提供

host 側は requirement ごとの満足可否を以下から判断する。

- 環境変数
- pytest option
- 設定ファイル
- fixture / plugin 拡張

初期案では環境変数 `ARDUINO_TEST_CAP_<name>` をサポートする。`.` や `-` は `_` に正規化し、大文字小文字を区別しない。

---

## 12. 成果物保存

### 12.1 保存先

host は成果物を pytest 実行結果に紐づくディレクトリへ保存する。

推奨 layout:

```text
artifacts/
  <test-name>/
    <filename>
```

### 12.2 filename 制約

host は以下の filename を拒否する。

- 絶対パス
- `..` を含む path
- 空文字
- device や OS に依存する制御文字を含む path

---

## 13. pytest fixture API 案

初期の `arduino_test` fixture は以下の API を持つ。

```python
def test_board(arduino_test):
    arduino_test.run()
```

想定 API:

```python
arduino_test.list_tests()
arduino_test.run()
arduino_test.run("test_name")
arduino_test.reset()
arduino_test.artifacts
arduino_test.metrics
```

- `run()` は実行可能な全テストを実行し、失敗があれば pytest failure に反映する
- `run("test_name")` は単一テストのみ実行する
- skipped は pytest skip / report に反映する
- metrics と artifacts は test report へ添付できる形で保持する

---

## 14. エラーと復旧

### 14.1 protocol error

host は以下を protocol error として扱う。

- 不明な message type
- 不正な field 数
- payload length と実データ長の不一致
- `RUN` に対する `RESULT` が timeout した
- 実行中 test と異なる test name の event を受け取った

### 14.2 reset

通信途絶、timeout、protocol error の後、host は必要に応じて reset を行う。reset の具体的な方法は `pytest-embedded-arduino-cli` 側が管理する。

---

## 15. 未決事項

- metadata 登録 API を案 A / 案 B のどちらにするか
- `RESET_STATE` で config を保持するか破棄するか
- `READY` を必須 event にするか、任意 event にするか
- `skipped` を device result として許可するか
- payload の文字コードを UTF-8 固定にするか、binary-safe とだけ定義するか
- artifact の分割送信を初期から入れるか
- metric の単位やタグを protocol に含めるか
