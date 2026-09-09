# テストの応用

[English](TESTING_ADVANCED.md)

[テストの基本](TESTING_BASICS.ja.md) の続きです。実機テストで踏みやすい落とし穴と、標準機能で足りないときの手段を扱います。

## pytest の基本の仕組み

このガイドで繰り返し出てくる 4 つの仕組みを、先にまとめます。

### テストの収集規則

pytest が自動で実行するのは、次の条件を満たすものだけです。

- ファイル名が `test_` で始まる `.py`
- その中の `test_` で始まる関数

**逆に言うと、`test_` を外せば自動では呼ばれません。** これは覚えておく価値があります。

いちばん多い用途は補助関数です。テストファイルに書くヘルパーは `test_` で始めてはいけません。始めてしまうと pytest がテストとして収集し、引数を fixture と解釈して失敗します。

```python
# ヘルパーは test_ で始めない
def wait_ready(dut):
    ...


def test_actual(dut):
    wait_ready(dut)
```

**テストファイルの名前は、プロジェクト全体で一意にしてください。** 同じ basename のファイルが 2 つあると、collection の時点でエラーになります。

```text
import file mismatch:
imported module 'test_plain' has this __file__ attribute:
  .../no_ino/test_plain.py
which is not the same as the test file we want to collect:
  .../with_ino/test_plain.py
```

`__init__.py` を置かないディレクトリでは、ファイルの basename がそのままモジュール名になるためです。sketch ディレクトリ名に合わせて `test_<sketch 名>.py` と付けておけば、自然に一意になります。

**同時に実行しないつもりのファイルでも一意にしてください。** 別々に動かしているうちは気づかず、あとで全体を流したときに初めて出ます。`--import-mode=importlib` を使えば重複を許せますが、名前を一意にするほうが単純です。

一時的にテストを止めたいときにも使えますが、その用途では勧めません。名前を変えると、止めていること自体が見えなくなります。理由が残る方法、つまり marker を使ってください。

### marker とは

marker はテストに付ける印です。`@pytest.mark.<名前>` の形でテスト関数に付けます。

pytest が意味を知っているものがいくつかあります。

| marker | 働き |
| --- | --- |
| `skip` | 常に飛ばす。理由を `reason` に書く |
| `skipif` | 条件が真のときだけ飛ばす |
| `xfail` | 失敗が既知。失敗しても全体は赤にならない |
| `parametrize` | 値を変えて同じテストを複数回実行する |

止めるならこう書きます。

```python
@pytest.mark.skip(reason="ハードウェア待ち")
def test_pending(dut):
    ...
```

これなら実行結果に skip として現れ、`reason` も表示されるので、止めていることと理由が残ります。名前から `test_` を外す方法との違いはここです。

**自分で名前を決めた marker も付けられます。** 意味は pytest が知らないので、`-m` での選別に使います。使う前に ini へ登録してください。登録しないと警告が出ます。`--strict-markers` を付けるとエラーになるので、綴り間違いを防げます。

```ini
[pytest]
markers =
    slow: 実行に時間がかかる
```

```bash
pytest -m "not slow"    # slow を除いて実行
pytest -m slow          # slow だけ実行
```

この形は、この後の「機材があっても既定から外したいとき」でも使います。

### conftest.py とは

`conftest.py` は、pytest が自動で読み込むファイルです。テストファイルと同じディレクトリか、その上位のディレクトリに置きます。import は不要で、置いてあれば読まれます。

**効く範囲は置いた場所の配下です。** プロジェクトの root に置けば全体に、sketch ディレクトリに置けばその sketch とその下だけに効きます。同じ名前の fixture が両方にあれば、テストに近いほうが勝ちます。

書けるものは主に 2 つです。

- **fixture の定義。** 複数のテストファイルで共有する準備や後片付けです。
- **hook の実装。** `pytest_runtest_setup` のように決まった名前の関数を書くと、pytest が適切な時点で呼び出します。「テストの前」「セッションの終わり」のような、fixture では表せない位置に処理を差し込めます。

強力ですが、使いどころは選んでください。理由と実際の用途は、後の「conftest.py は最後の手段」で扱います。

### 設定ファイル: pytest.ini と pyproject.toml

pytest の設定は 1 つのファイルから読まれます。候補は 4 つあり、上にあるものが勝ちます。

1. `pytest.ini` の `[pytest]`
2. `pyproject.toml` の `[tool.pytest.ini_options]`
3. `tox.ini` の `[pytest]`
4. `setup.cfg` の `[tool:pytest]`

`pytest.ini` は中身が空でも勝ちます。**2 つ置くと片方は完全に無視されます。** 設定を書いたのに効かないときは、まずどちらが読まれているかを疑ってください。実行時の出力に `configfile:` として表示されます。

書き方は形式によって違います。

```ini
# tests/pytest.ini
[pytest]
testpaths = unit suites
addopts = -m "not manual"
markers =
    manual: 人の操作を必要とする
```

```toml
# tests/pyproject.toml
[tool.pytest.ini_options]
testpaths = ["unit", "suites"]
addopts = "-m 'not manual'"
markers = [
    "manual: 人の操作を必要とする",
]
```

TOML では値に型があるので、複数行の設定は配列で書きます。`addopts` のように引用符を含む値は、外側と内側で別の引用符を使ってください。

よく使う項目です。

| 項目 | 働き |
| --- | --- |
| `testpaths` | 引数なしで実行したときの対象ディレクトリ |
| `addopts` | 毎回付ける option |
| `markers` | 自作 marker の登録 |
| `filterwarnings` | warning の扱い |

この plugin のリポジトリでは `pyproject.toml` に `testpaths = ["tests"]` を書いているため、引数なしの `pytest` は plugin 自身のテストだけを実行します。`examples/` を動かすときは対象を明示します。

環境によって有効無効が変わるテストの分け方は、次の節で扱います。

## 常設の機材と、そのときだけの機材

治具は 2 種類に分かれます。

- **常設の機材。** いつも繋がっていて、既定の実行で使えます。
- **臨時のもの。** 特定のテストのときだけ用意するものです。追加の board、センサ、アナライザ、給電を切れる装置のほか、**人の操作そのものも含まれます。** ボタンを押す、ケーブルを抜き差しする、磁石を近づける、といったテストは、人がその場にいる時間しか実行できません。

**分ける基準は台数ではなく、既定の実行でいつも揃うかどうかです。** 機材でも人でも同じ扱いです。常設が 3 台あるなら 3 台のテストを既定に入れてよく、常設が 1 台なら 2 台のテストが臨時扱いになります。

### peer の board は plugin が面倒を見ます

port か profile が解決できない peer があると、**その peer を使うテストは skip になります**。失敗しません。

```text
SKIPPED [1] peer device2: port is not resolved
```

つまり追加の board のために conftest を書く必要は、多くの場合ありません。繋いで port を設定した環境ではそのまま走り、繋いでいない環境では静かに skip されます。CI と実験机で同じテストファイルを共有できます。

### plugin が知らない機材は自分で判定します

センサやアナライザ、給電を切れる装置のように、plugin が存在を知らない機材は、自分で有無を確かめて skip します。

```python
# manual/conftest.py
import os

import pytest


def pytest_runtest_setup(item):
    if not os.environ.get("TEST_POWER_SWITCH"):
        pytest.skip("給電を切れる装置が設定されていません")
```

conftest をディレクトリに置けば、その配下だけに効きます。

### 自動で判定できないものは既定から外す

**人の操作が必要なテストは、環境変数では判定できません。** その場に人がいるかどうかを plugin もテストも知りようがないからです。実行に非常に時間がかかるテストも、機材は揃っているが毎回は流したくない類です。こうしたものは既定の実行から外し、必要なときだけ指定します。方法は 3 つです。

**ディレクトリで分ける。** `testpaths` の対象から外し、必要なときだけ指定します。

```bash
pytest                 # testpaths のものだけ。manual は入らない
pytest manual/         # 必要なときだけ
```

**marker で分ける。** ini に登録し、既定では除外します。

```ini
[pytest]
markers =
    manual: いつも繋がっていない機材や人の操作を要求する
addopts = -m "not manual"
```

```bash
pytest -m manual       # marker を付けたものだけ
```

**ファイル名から `test_` を外す。** 収集規則を逆に使う方法です。ファイル名が `test_*.py` でなければ自動では収集されませんが、**ファイルを直接指定したときだけパターン照合が飛ばされ、収集されます**。

テストファイルは sketch ディレクトリの中に置く必要があるので、`manual/` の直下ではなく sketch ごとのディレクトリに入れます。

```text
  manual/
    manual_power_cycle/
      manual_power_cycle.ino
      sketch.yaml
      manual_power_cycle.py   <- test_ で始まらない
```

```python
# manual/manual_power_cycle/manual_power_cycle.py
def test_power_cycle(dut):     # 関数側の test_ は必要
    ...
```

```bash
pytest                                                  # 収集されない
pytest manual/                                          # 収集されない
pytest manual/manual_power_cycle/manual_power_cycle.py  # これだけ収集される
```

**ディレクトリ指定では収集されない点に注意してください。** ファイルを名前で指定する必要があります。まとめて動かすなら shell の展開を使います。

```bash
pytest manual/*/*.py
```

ini への登録も `testpaths` の調整も要らないので、**1 本ずつ動かすテストには手軽です。** 人が操作するテストはたいてい 1 本ずつ動かすので相性が良いです。代わりに、そのファイルにテストが入っていることが名前から分かりにくくなります。まとめて流すことが多いなら、ディレクトリか marker のほうが向いています。

どの方法でも構いません。要点は、**機材や人が揃わない環境で必ず失敗するテストを既定の実行に置かないこと**です。置くと失敗が常態になり、本当の失敗が埋もれます。

## 設定の優先順位と `.env`

port と define を環境ごとに差し替える仕組みです。[基本](TESTING_BASICS.ja.md) で触れた `.env` の全体像を並べます。

### primary DUT の port

上にあるものが勝ちます。

1. `--flash-port`
2. `--port`
3. `TEST_SERIAL_PORT_<PROFILE>`
4. `TEST_SERIAL_PORT`
5. `sketch.yaml` の `profiles.<profile>.port`。ただし `socket://...` の場合だけ

`<PROFILE>` は profile 名を大文字にし、`-` を `_` に置き換えたものです。

### peer DUT の port

peer は primary の指定を引き継ぎません。名前ごとに解決します。

1. `--peer-port <name>:<port>`
2. `TEST_SERIAL_PORT_PEER_<NAME>_<PROFILE>`
3. `TEST_SERIAL_PORT_PEER_<NAME>`
4. `sketch.yaml` の `socket://...`
5. 解決できなければ、その peer を使うテストは skip

`<NAME>` は `peer_` を除いたディレクトリ名を大文字にしたものです。`peer_echo` なら `ECHO` です。

### compile 時の define

`build_config.toml` の `[defines]` は、左が環境変数名、右が C/C++ 側の define 名です。

```toml
[defines]
TEST_WIFI_SSID = "WIFI_SSID"
TEST_WIFI_PASSWORD = "WIFI_PASSWORD"
```

```bash
# .env
TEST_WIFI_SSID=my-ssid
TEST_WIFI_PASSWORD=my-password
```

環境変数が未設定でも空文字が渡され、エラーにはなりません。値が必要なら、空文字を弾く判定を sketch 側かテスト側に書いてください。

### 使い分け

- **`.env`**: その machine の常設設定。git に入れません。
- **コマンドラインの option**: 一時的な上書き。`.env` より強いので、別の board を試すときに使います。
- **`sketch.yaml` の `socket://`**: host core のように board に依存しない接続先。リポジトリに入れて共有できます。

CI では `.env` を置かず、secret から環境変数として渡す形が扱いやすいです。host core だけを回すなら port の指定は不要で、`sketch.yaml` の `socket://localhost` がそのまま使われます。

## expect の落とし穴

### 末尾の可変長フィールドは行末で止める

シリアルの 1 行は分割して届きます。pattern の最後が可変長で、しかも改行で止めていないと、行の残りが届く前に match が確定し、切り詰めた値を取り出します。

実際に `data=abcdef12` を出力した相手から `data=abcdef1` を読み取った例があります。

```python
# 悪い例。最後の capture が途中で確定しうる
dut.expect(re.compile(rb"data=([0-9a-f]+)"))

# 良い例。行末で止める
dut.expect(re.compile(rb"data=([0-9a-f]+)\r?\n"))
```

capture の後ろに同じ pattern 内の別のリテラルが続く場合は、そのリテラルが届くまで match しないので問題ありません。

### マッチした後の出力は保証されない

`dut.expect(...)` は pattern がマッチした時点で読み取りを終えます。その後にデバイスが送るバイトは `dut.log` に届く保証がなく、行の途中で切れることがあります。末尾まで確実に残したいときは、終端マーカーを出して `expect` するか、明示的にドレインします。

```python
import pexpect

dut.expect_exact("確認したい最後の行")
dut.expect(pexpect.TIMEOUT, timeout=2)   # 残りを読み切る
```

## ログとアーティファクトの置き場所

2 種類あり、扱いが違います。

**シリアルログは `pytest-embedded` が管理します。** 実行ごとに UTC タイムスタンプ付きのディレクトリが作られ、その下にテストごとのディレクトリと `dut.log` が置かれます。**実行ごとに別のディレクトリなので、前回のログが上書きされることはありません。** 置き場所は `--root-logdir` で変えられます。この plugin は同じディレクトリに結果ファイル（`PASSED.txt` / `FAILED.txt` など、`SUMMARY.txt`、`summary.json`）も書きます。

つまり**実行後のログ退避は、多くの場合そもそも不要です**。CI で成果物として特定の場所へ集めたい、あるいは溜まり続けるのを整理したい、という要求があるときだけ考えてください。

**sketch 自身が書き出すファイルは別物です。** host core で動かす sketch が `fopen("output/...", ...)` のように書き出す場合、実行時のカレントディレクトリは sketch ディレクトリなので、ファイルは `tests/<name>/output/` に落ちます。ここは実行ごとに分かれないので、**前回のファイルが残ります**。残っていると、失敗した実行が成功に見えることがあります。これを消すのが、次の節でいちばん多く出てくる conftest の用途です。

## 中断時の後片付け

テストが途中で落ちると、末尾に書いた片付けは実行されません。`assert` の失敗、`expect` の時間切れ、Ctrl-C のいずれでも同じです。ボードは中途半端な状態のまま残ります。

同じ module に次のテストがあればそれを巻き込み、なければ実行終了後もその状態が続きます。BLE のアドバタイズを出したまま終われば、隣の治具のスキャンに映り続けます。

pytest の fixture の後処理は、テストが失敗しても Ctrl-C でも実行されます。これを使います。

```python
# tests/device/conftest.py  ... このディレクトリ配下のテストは全部 dut を使う前提
import pytest


@pytest.fixture(autouse=True)
def leave_quiet(dut):
    yield
    dut.write("stop\n")
    try:
        dut.expect_exact("STOPPED", timeout=2)
    except Exception:
        pass
```

制約が 2 つあります。

- **`dut` を要求する autouse fixture は、そのディレクトリ配下の全テストにボードを要求します。** 実機を使わないユニットテストが混ざっている場所には置けません。デバイステストだけが入っているディレクトリの conftest に置いてください。
- **peer には届きません。** autouse fixture が `peers` を要求すると、peer の有効化判定に引っかかり、全テストが peer テスト扱いになって毎回 peer の build と upload が走ります。

何を止めるかはプロジェクト次第です。実績のある判断はこうです。

- **BLE のアドバタイズとスキャンは必ず止める。** 止めないと周囲の治具に干渉します。
- **PWM、サーボ、GPIO の駆動は止めたほうがよい。** 物理的に動き続けるものは危険です。
- **USB のようなペリフェラルは、止めなくても実害が小さいことがあります。** Arduino の USB スタックは一度 begin すると device の提示を止められません。止められないものは、止められる範囲で片付けて構いません。
- **応答は「受け取った」ではなく「その状態に到達した」ときに返す。** 再アドバタイズの開始や接続の全切断には時間がかかります。受信直後に返すと、まだ終わっていない状態で次へ進みます。

**後片付けはテスト開始時の正規化の代わりにはなりません。** 後片付けが守るのは環境です。テスト自身の正しさと、`-k` で 1 本だけ回せることは、開始時の正規化が担います。前のテストの後片付けが成功した前提でテストを書かないでください。

## conftest.py は最後の手段

`conftest.py` は pytest の拡張点です。テストファイルと同じディレクトリか、その上位のディレクトリに置くと効きます。上位に置けばプロジェクト全体、sketch ディレクトリに置けばその sketch だけ、と範囲を選べます。

**まず標準機能で足りないか確かめてください。** この plugin が用意しているものは次の通りで、多くの要求はこれで済みます。

- profile の選択（`--profile`、`sketch.yaml` の `default_profile`）
- port の解決（`--port`、`TEST_SERIAL_PORT_<PROFILE>`、`sketch.yaml` の `socket://`）
- 実行範囲の制御（`--run-mode=all|build|test`）
- compile-time define の注入（`build_config.toml`）
- peer DUT（`peer_<name>/` と `peers`）
- 物理デバイスの排他（`--device-lock`）
- 結果 summary（log directory への出力）
- デバイス側アサーション（Unity、ArduTest）

それでも conftest が必要になる場面はあります。以下は実際のプロジェクトで使われている形です。

### 1. sketch が書き出したファイルを実行前に消す

いちばん多い用途です。前回のファイルが残っていると、失敗した実行が成功に見えます。

```python
import shutil
from pathlib import Path


def pytest_runtest_setup(item):
    output_dir = Path(item.fspath).parent / "output"
    if output_dir.exists():
        shutil.rmtree(output_dir)
```

**fixture ではなく hook にする理由があります。** `pytest_runtest_setup` は `dut` fixture が sketch を build して起動する前に走ります。fixture で書くと、消す処理が sketch の書き込みと競合しかねません。順序を確実にするために hook を使います。

注意点として、この形は `output` という名前のディレクトリを無条件に削除します。他のリポジトリへ持っていくときは中身を確認してください。

### 2. compile より前に設定を書き換える

sketch.yaml の platform version を実行のあいだだけ差し替える、といった用途です。

```python
def pytest_collection_finish(session):
    # plugin が compile を始める前に書き換える
    ...


def pytest_sessionfinish(session, exitstatus):
    # 元に戻す
    ...
```

**`pytest_collection_finish` を使う理由**は、fixture の順序に関係なく compile より前だと保証できることです。書き換えと復元のあいだで異常終了すると作業ツリーが書き換わったまま残るので、実際の実装ではリポジトリ外にも元の内容を退避しています。

### 3. 複数の sketch で使う問い合わせヘルパーを共有する

[基本](TESTING_BASICS.ja.md) の方法 A を fixture にした形です。suite をまたいで使うので conftest に置きます。

```python
import pexpect
import pytest


@pytest.fixture
def probe():
    def ask(target, command, pattern, attempts=12, timeout=5):
        for _ in range(attempts):
            target.write(command)
            try:
                return target.expect(pattern, timeout=timeout)
            except pexpect.TIMEOUT:
                continue
        raise AssertionError(f"no answer to {command!r} matching {pattern!r}")

    return ask
```

### 4. シリアルログを検査して報告に足す

テストは通ったが、ログに気になる行が出ていた、という状況を拾う用途です。fixture でログを読み、`pytest_runtest_makereport` で報告に節を足し、`pytest_terminal_summary` で全体をまとめます。**報告に関わる hook が必要なので、conftest でしか書けません。**

このとき**その fixture に `dut` を要求させないでください**。要求すると `dut` より後に setup され、`dut` より先に後処理が走るため、ログの末尾を読めなくなります。`test_case_tempdir` だけを要求すれば正しい順序になります。

### 5. 実行前に環境を用意する

ローカルの platform を Arduino のディレクトリへ symlink する、といった準備を session 単位で行う用途です。build より前に一度だけ実行する必要があるので、session scope の autouse fixture にします。

### 6. 実機を使わないユニットテストのヘルパー

`tests/` の下には、ボードを使わない純粋な Python のテストも置けます。`.ino` がないディレクトリに置けば、この plugin は compile も upload も行わず、普通の pytest として動きます。その fixture は通常の pytest の使い方で、plugin とは無関係です。

### conftest が不要なケース

- **1 つのテストファイルの中だけで使うヘルパー。** そのファイルに普通の関数として書けば足ります。
- **port や profile の切り替え。** option と環境変数で足ります。
- **テストごとの初期化。** テスト本文の先頭に書くほうが、読み手に見えます。

## ボードの状態を観測する

実行が終わった後にボードの状態を確かめたくなりますが、**同じボードに繋いで聞くと答えは信用できません。**

シリアルポートを開くと、pyserial が DTR と RTS を立てます。plugin がリセットのために操作しているのではなく、ポートを開く既定の動作です。この 2 線を EN に直結している board では、これがそのままリセットになります。つまり問い合わせに答えるのは、起動し直した sketch です。停止したはずのアドバタイズを確かめたら起動時の状態が返り、失敗したように見えます。開く前に両線を落としても同じです。実際に peer は `ADVERTISING 1` と答え、Classic の DUT は起動時出力をそのまま流しました。

**リセットされるかは board によります。** 自動リセット回路を挟んでいる board では、開いただけではリセットされないことが多いです。native USB CDC の board も通常はリセットされませんが、1200 bps で開くと再起動します。**どちらであっても、対象の board に繋いで確かめる方法は信用できません。** リセットされる board では起動状態を読み、されない board でも接続そのものが sketch の動作に影響しうるからです。

**観測は別のボードから行ってください。** 対象には触れず、もう 1 台に観測用の sketch を焼いて聞きます。そして**対照も取ってください**。「聞こえない」だけなら、観測側が壊れていても同じ結果になります。対象をリセットして起動状態に戻し、同じ観測側で聞こえることを確認します。

### DTR と RTS を触らない option がない理由

plugin にはこの動作を変える option がありません。意図的にそうしています。

まず、**「触らない」という選択は存在しません。** ポートを開いた後、2 線には必ず何らかのレベルが乗ります。assert をやめても、解除側に落ちるかドライバが持っていた状態が残るだけです。古典的な ESP32 の回路では DTR が IO0、RTS が EN に繋がっているので、解除側で保持すると次のリセットで書き込みモードに入りかねません。つまり option は「触らない」ではなく「どちらのレベルで開くか」になり、正しい値は board ごとに違います。

次に、**テストがステートレスなら接続時のリセットは無害です。** 各テストが自分で状態を作るので、リセットされても困りません。困るのは module 内で状態を積み上げるテストですが、それは避けるべき書き方です。

必要になりうる条件は 1 つだけ考えられます。**接続でリセットされる board で、かつ起動に数秒かかる構成**です。module に複数テストがあると毎テスト起動待ちを払います。1 module 1 テストなら upload の時間が支配的なので、差はほぼ出ません。

どうしても必要なプロジェクトには逃げ道があります。`pytest-embedded` の `Serial` は、port 文字列の代わりに構築済みの pyserial オブジェクトを受け取れます。conftest で `serial` fixture を上書きし、`do_not_open=True` で用意して DTR と RTS を設定してから開く形が取れます。board 固有の判断になるので、plugin の option より conftest 向きの内容です。

## peer テストの原則

2 台以上のテストで実績のある方針です。

- **テスト専用の識別子で相手を絞る。** BLE ならテスト専用の 128-bit Service UUID を使い、周囲の機器を除外します。device name だけで接続相手を決めないでください。
- **両側のシリアルログだけで合否を判定できる形にする。** 片側からの推測に頼らないと、どちらが悪いのか分かりません。
- **各テストの終了時に、スキャン、アドバタイズ、購読、接続を止める。**
- **無線環境による一時的な遅延には timeout を許すが、無制限の retry はしない。** 無制限に retry すると不具合を隠します。
- **切断理由、MTU、セキュリティ状態は、可能な範囲で両側で照合する。**
- **可能なら一方を標準ライブラリの直接実装にする。** 自作ライブラリ同士では相互接続性が確かめられません。
- **状態を持つテストは、開始時と終了時の状態を明示する。** Bond や NVS のように実行をまたいで残るものは特にそうです。

## 起動時に外へ影響を出さない

peer を使う構成では、書き込みの順序に注意が必要です。primary の upload は module 単位で先に走り、peer の upload は最初のテストの setup 中に走ります。つまり **primary が起動して `setup()` を実行した後に、peer が書き込まれます**。

primary が `setup()` で無線や USB を有効にしていると、peer の書き込み中のリセットや列挙を観測してしまい、エラーとして記録されることがあります。sketch の不具合ではありません。

対策は、**`setup()` では外へ影響する動作を始めず、テストから指示されてから始めること**です。テスト本文の 1 行目で有効化すれば、peer の書き込みは既に終わっています。
