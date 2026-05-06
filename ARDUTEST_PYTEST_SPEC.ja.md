# ArduTest pytest 連携仕様（ドラフト）

## 1. 概要

本仕様は、`pytest-embedded-arduino-cli` が提供する `arduino_test` fixture の要件を定義する。

`arduino_test` fixture は、Arduino 側ライブラリ `ArduTest` と通信し、テスト一覧の取得、requirement / config の評価、テスト実行、結果収集、pytest result への反映を担当する。

通信 protocol の command / event / payload 形式は [`ARDUTEST_PROTOCOL_SPEC.ja.md`](ARDUTEST_PROTOCOL_SPEC.ja.md) で定義する。本仕様では pytest 側の公開 API、設定解決、実行ライフサイクル、pytest への反映方法を扱う。

---

## 2. 目的

- Arduino 側に書かれた ArduTest テストを pytest から実行できること
- 実行前に requirement / config requirement を評価し、実行可否を決定できること
- Arduino 側の pass / fail / error を pytest result に反映できること
- ログ、メトリクス、成果物を pytest 側で保存・参照できること
- 既存の `dut` fixture 利用テストに影響を与えないこと

---

## 3. 非目的

- `dut.expect(...)` を置き換えること
- Unity 出力 parser の置き換え
- Arduino 側ライブラリ API の定義
- 外部測定機器の直接制御
- device farm や複数ボード並列制御

---

## 4. fixture の位置づけ

`arduino_test` は、`pytest-embedded-arduino-cli` 上に追加される高水準 fixture である。

```python
def test_board(arduino_test):
    arduino_test.run()
```

内部的には以下を利用してよい。

- `arduino_cli_app`
- `arduino_cli_build`
- `arduino_cli_upload`
- `dut`
- `pytest-embedded-serial`

ただし、利用者が既存どおり `dut` を直接使うテストには影響を与えない。

---

## 5. 公開 API

### 5.1 `arduino_test.run()`

実行可能な全 ArduTest テストを実行する。

```python
def test_board(arduino_test):
    arduino_test.run()
```

挙動:

- 必要なら初期同期を行う
- テスト一覧を取得する
- requirement と config requirement を評価する
- skip 対象以外を 1 件ずつ実行する
- failed または error があれば pytest failure に反映する
- skipped は pytest report に反映する

### 5.2 `arduino_test.run(name)`

指定された 1 件の ArduTest テストだけを実行する。

```python
def test_wifi(arduino_test):
    arduino_test.run("test_wifi_connect")
```

指定名が存在しない場合は pytest error とする。

### 5.3 `arduino_test.list_tests()`

初期同期と `LIST` を実行し、device 側のテスト metadata を返す。

```python
tests = arduino_test.list_tests()
```

戻り値は Python 側の dataclass または同等の読み取り専用オブジェクトとする。

想定フィールド:

- `name`
- `requirements`
- `required_configs`

### 5.4 `arduino_test.reset()`

device reset または protocol 状態 reset を行う。

初期実装では、物理 reset の有無は `pytest-embedded-arduino-cli` の既存 reset 能力に従う。protocol のみの reset が可能な場合は `RESET_STATE` を送る。

### 5.5 収集データ

実行後、以下を参照できる。

```python
arduino_test.results
arduino_test.logs
arduino_test.metrics
arduino_test.artifacts
```

初期実装では、これらは fixture インスタンス上の属性として保持する。pytest report への添付方式は別途検討する。

---

## 6. 内部データモデル

### 6.1 Test metadata

```python
ArduTestCase(
    name: str,
    requirements: tuple[str, ...],
    required_configs: tuple[str, ...],
)
```

### 6.2 Test result

```python
ArduTestResult(
    name: str,
    status: Literal["passed", "failed", "skipped", "error"],
    failures: list[ArduTestFailure],
    logs: list[str],
    metrics: dict[str, int | float],
    artifacts: list[ArduTestArtifact],
    duration: float,
    skip_reason: str | None,
)
```

### 6.3 Artifact

```python
ArduTestArtifact(
    test_name: str,
    filename: str,
    content_type: str,
    path: Path,
)
```

---

## 7. 実行ライフサイクル

### 7.1 通常実行

```text
1. pytest fixture setup
2. arduino-cli build / upload は既存 autouse fixture に従う
3. dut / serial 接続を確立
4. protocol HELLO
5. LIST で test metadata を取得
6. capability / config を評価
7. device へ config を送信
8. RUN を 1 件ずつ送信
9. event を収集
10. pytest result へ反映
```

### 7.2 lazy sync

`arduino_test` は fixture 生成時には device と通信しなくてよい。`run()` または `list_tests()` が呼ばれた時点で初期同期する。

理由:

- `arduino_test` fixture を引数に取るだけで serial を消費しない
- ユーザーが独自制御したい場合に余地を残す
- pytest collection 段階では device 接続を前提にしない

### 7.3 複数回 run

同じ pytest test function 内で複数回 `run()` が呼ばれた場合、初期同期結果は再利用してよい。

config や capability を変更したい場合は、明示 API を追加するまでは同一 fixture 内では非対応とする。

---

## 8. pytest 結果への反映

### 8.1 status mapping

| ArduTest status | pytest 側の扱い |
| --- | --- |
| `passed` | pass |
| `failed` | assertion failure |
| `error` | pytest error または failure |
| host-side `skipped` | skip report |

初期実装では、1 つの pytest test function 内で複数の ArduTest テストを実行した場合、いずれかが failed / error なら pytest test function 全体を failure にする。

### 8.2 複数テスト結果の表示

`arduino_test.run()` は、失敗時に以下を含む summary を pytest failure message に含める。

- failed / error の test name
- assertion failure の file / line / expression
- protocol error の code / message
- skipped の件数

### 8.3 pytest item 分割

ArduTest の各 test case を pytest item として collection する方式は初期実装では採用しない。

理由:

- pytest collection 時点で device 接続や firmware 実行を必要とする
- build / upload / serial lifecycle と衝突しやすい
- 初期実装では fixture API の方が単純

将来、`--arduino-test-collect` のような opt-in 機能として検討してよい。

---

## 9. capability

### 9.1 requirement 評価

device から取得した requirement は host 側 capability と照合する。

満たされない requirement を持つテストは `RUN` せず skipped とする。

### 9.2 環境変数

初期実装では以下の形式をサポートする。

```text
ARDUINO_TEST_CAP_<NAME>=true
```

正規化:

- requirement 名の `.`、`-`、`:` は `_` に変換する
- 大文字小文字は区別しない

例:

```text
measurement.current -> ARDUINO_TEST_CAP_MEASUREMENT_CURRENT
network -> ARDUINO_TEST_CAP_NETWORK
```

true とみなす値:

- `1`
- `true`
- `yes`
- `on`

false とみなす値:

- 未設定
- `0`
- `false`
- `no`
- `off`

その他の値は設定不備として pytest error にする。

### 9.3 pytest option

将来、以下の option を追加してよい。

```text
--arduino-test-capability=name
--arduino-test-capability=name=true
--arduino-test-capability=name=false
```

初期実装では環境変数のみでもよい。

---

## 10. config

### 10.1 config 提供元

初期実装では以下から config を取得する。

1. pytest option
2. 環境変数
3. pytest ini

ただし、最初の実装では環境変数のみでもよい。

### 10.2 環境変数

初期実装では以下の形式をサポートする。

```text
ARDUINO_TEST_CONFIG_<NAME>=value
```

正規化規則は capability と同じとする。

例:

```text
ssid -> ARDUINO_TEST_CONFIG_SSID
wifi.password -> ARDUINO_TEST_CONFIG_WIFI_PASSWORD
```

### 10.3 必須 config 不足

`REQUIRE_CONFIG` で宣言された config が見つからない場合、既定では skipped とする。

以下の option で error 扱いへ切り替えられる。

```text
--arduino-test-missing-config=skip|error
```

### 10.4 device への送信

host は実行対象テストが要求する config だけを `SET_CONFIG` で送る。

同じ config を複数テストが要求する場合は 1 回だけ送ってよい。

---

## 11. logs / metrics / artifacts

### 11.1 logs

`LOG` event は test result に紐づけて保持する。

pytest の `-s` や verbose mode で表示するかどうかは別途 option 化してよい。

### 11.2 metrics

`METRIC` event は test name ごとに保存する。

同じ metric name が複数回送られた場合、初期実装では list として保持するか、最後の値のみ保持するかを未決事項とする。

### 11.3 artifacts

`ARTIFACT_TEXT` / `ARTIFACT_BINARY` はファイルとして保存する。`ARTIFACT_TEXT` は UTF-8 text として保存し、`ARTIFACT_BINARY` は payload bytes を decode せずそのまま保存する。

保存先 root は pytest option で指定できる。

```text
--arduino-test-artifact-dir=PATH
```

既定値は `ardutest` とする。

`PATH` が相対 path の場合は pytest の `rootdir` からの相対 path として解決する。したがって既定の保存先は `<pytest rootdir>/ardutest` となる。

保存 layout:

```text
<artifact-dir>/<test-name>/<filename>
```

`<artifact-dir>` は artifact を保存する必要がある時点で自動生成する。artifact が 1 件も発生しない実行では、空の artifact directory を作成しない。

初期実装では pytest の `tmp_path` 系 fixture に依存せず、option で指定された artifact root と `request.node` から安定した保存先を決める。

`--clean` が指定されている場合、テスト実行前に `<artifact-dir>` を directory ごと削除する。その後も通常実行と同じく、artifact を保存する必要がある時点まで directory は再作成しない。

filename は protocol 仕様に従い検証する。

---

## 12. timeout / reset / error

### 12.1 timeout

timeout は host 側で判定する。

推奨 option:

```text
--arduino-test-timeout=30
```

単位は秒。初期値は 30 秒を候補とする。

### 12.2 protocol error

以下は protocol error とする。

- 不明な event
- field 数の不一致
- payload 長の不一致
- 実行中ではない test の `RESULT`
- `RUN` 後に timeout まで `RESULT` が来ない

protocol error は pytest error とし、可能であれば reset を試みる。

### 12.3 reset

`arduino_test.reset()` は以下の順で実行できるものとする。

1. protocol `RESET_STATE`
2. 利用可能なら serial / board reset
3. 必要なら再同期

どこまで実装できるかは既存の `pytest-embedded` / serial 層に依存する。

---

## 13. pytest option 案

初期候補:

```text
--arduino-test-timeout=SECONDS
--arduino-test-missing-config=skip|error
--arduino-test-artifact-dir=PATH  # default: ardutest
```

将来候補:

```text
--arduino-test-capability=NAME[=BOOL]
--arduino-test-config=NAME=VALUE
--arduino-test-show-log
--arduino-test-collect
```

option は既存の `arduino-cli` option と衝突しない名前にする。

---

## 14. 実装モジュール案

```text
src/pytest_embedded_arduino_cli/
  ardutest.py
  ardutest_protocol.py
```

### 14.1 `ardutest_protocol.py`

- command の生成
- event parser
- payload reader
- protocol error 定義

### 14.2 `ardutest.py`

- `arduino_test` fixture の実体
- metadata / result dataclass
- capability / config 評価
- run lifecycle
- artifact 保存

`plugin.py` には fixture 登録と option 登録だけを置き、詳細ロジックは上記モジュールへ分離する。

---

## 15. テスト方針

### 15.1 unit test

- protocol parser
- command 生成
- payload length 処理
- capability env var 正規化
- config env var 正規化
- requirement による skip 判定
- result aggregation
- artifact filename 検証

### 15.2 integration test

初期段階では実 serial なしで、fake DUT / fake stream を使って以下を検証する。

- `HELLO` / `LIST` / `RUN` の標準フロー
- failed result の pytest failure 反映
- missing config の skipped 反映
- artifact 保存

実機例は後段で `examples/` に追加する。

---

## 16. 未決事項

- 初期実装で環境変数以外の config provider を入れるか
- metrics の同名複数値を list にするか最後の値にするか
- artifact root の既定値
- protocol error を pytest error と failure のどちらで表現するか
- `arduino_test.run()` で skipped だけだった場合の pytest result を pass にするか skip にするか
- pytest item 分割を将来実装するか
