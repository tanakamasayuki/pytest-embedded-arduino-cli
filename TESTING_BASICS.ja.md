# テストの基本

[English](TESTING_BASICS.md)

この plugin で初めてテストを書く人向けのガイドです。pytest 自体が初めてでも読めるように、テストとは何かから始めます。

## テストとは何か

これまで手で確認していたことを、機械に毎回同じ手順で確認させる仕組みです。

マイコンの開発では、sketch を書き込み、シリアルモニタを開き、出力を目で見て、コマンドを打って反応を確かめる、という作業を繰り返します。テストはこの手順をコードに書き写したものです。一度書けば、変更するたびに同じ確認が自動で走ります。

この plugin でのテストは、次の 1 行に尽きます。

**sketch をボードに書き込み、シリアル経由でやり取りし、期待した出力が出るか確かめる。**

## 用語

このガイドで使う言葉を先に決めておきます。

| 言葉 | 意味 |
| --- | --- |
| host | テストを動かす PC。pytest が動いている側です。 |
| device | テスト対象のマイコン基板。ボードとも呼びます。 |
| DUT | Device Under Test の略。テスト対象の device を指します。テスト関数の `dut` 引数がこれです。 |
| peer | DUT の通信相手になる device。1 台に限らず、必要な数だけ置けます。 |
| sketch | Arduino のプログラム。`.ino` ファイルです。 |
| profile | どの board 向けにどうビルドするかの設定。`sketch.yaml` に書きます。 |
| host core | sketch を host 用にビルドし、PC のプログラムとして動かす board core。マイコンを使いません。 |

host と device の 2 つは、この後ずっと出てきます。**host 側**と言うときは、pytest が動いている PC の側を指します。合否をどちら側で判定するか、という話で出てきます。**device 側**は、テスト対象のマイコン基板の側です。

これとは別に **host core** という言葉が出てきます。これは board core の一種で、sketch をマイコン向けではなく PC のプログラムとしてビルドし、PC 上で動かすものです。「host 側で判定する」と「host core で動かす」は別の話なので、混同しないでください。

## どういう仕組みで動くか

`pytest` を実行すると、次の順に進みます。

1. pytest が `test_` で始まる関数を集めます。これが実行されるテストです。
2. plugin が、そのテストファイルと同じディレクトリにある `.ino` を `arduino-cli` で compile します。
3. ボードへ upload します。ここでボードがリセットされ、sketch が動き始めます。
4. シリアルポートを開きます。
5. テスト関数が動きます。`dut.write(...)` で送り、`dut.expect_exact(...)` で待ちます。
6. 期待した文字列が来れば次へ進み、来なければ時間切れで失敗します。
7. シリアルポートを閉じます。

いちばん小さな組み合わせはこれです。sketch とテストの 2 つのファイルが対になります。

```cpp
// hello.ino
void setup()
{
  Serial.begin(115200);
  delay(1000);
  Serial.println("hello from arduino");
}

void loop()
{
}
```

```python
# test_hello.py
def test_hello(dut):
    dut.expect_exact("hello from arduino")
```

sketch が `Serial.println` で出した 1 行を、テストが `dut.expect_exact` で待っています。この対応が基本形です。

`Serial.begin(115200)` の速度は、テスト側と合わせてください。この plugin の既定は 115200 で、変えたいときは `--baud` を使います。ここが食い違うと文字化けした行が届きます。

テスト関数の引数に `dut` と書くだけで、上の 2 から 4 が自動で行われます。

送ってから応答を確かめる形も同じです。sketch 側は 1 行ずつ読んでコマンドとして扱います。

```cpp
// echo.ino
void setup()
{
  Serial.begin(115200);
}

void loop()
{
  if (Serial.available() == 0)
  {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();

  if (line == "ping")
  {
    Serial.println("PONG");
  }
}
```

```python
# test_echo.py
def test_echo(dut):
    dut.write("ping\n")
    dut.expect_exact("PONG")
```

`dut.write` が送った `ping` を sketch が読み、`PONG` を返し、それをテストが待ちます。この後の例もすべてこの形です。

大文字と小文字を使い分けているのは意図的です。**host から送るコマンドは小文字、device が出す結果の行は大文字**にしています。規則ではありませんが、ログを見たときにどちら向きの行か一目で分かるので、このガイドでは通してこうしています。

### 合否を判定する場所は 2 つある

- **host 側で判定する。** テストコードが受け取った文字列を確かめます。sketch は値を print するだけで済みます。ここまでの例はこれです。
- **device 側で判定する。** 判定を sketch の中で行い、結果だけを出力します。ボードの中の値を直接調べたいときに向いています。

device 側で判定する形は、素朴に書けばこうなります。

```cpp
  int sum = add(2, 3);
  if (sum == 5)
  {
    Serial.println("ADD_PASS");
  }
  else
  {
    Serial.print("ADD_FAIL sum=");
    Serial.println(sum);
  }
```

```python
def test_add(dut):
    dut.expect_exact("ADD_PASS")
```

判定が sketch 側にあるので、テストは結果の 1 行を待つだけです。

これを整えたものが Unity や ArduTest のようなライブラリです。仕組みはこうなります。

1. sketch が複数の検査を自分で実行します。
2. 各検査の結果と、成功した件数と失敗した件数をシリアルに出力します。
3. テスト側は 1 行でその出力を読み取ります。Unity なら `dut.expect_unity_test_output()`、ArduTest なら `arduino_test.run()` です。
4. **失敗が 1 件でもあれば、その pytest のテストが失敗します。** どの検査が失敗したかがエラーに出ます。

```python
def test_unity(dut):
    dut.expect_unity_test_output(timeout=60)   # 失敗が 1 件でもあればここで失敗する
```

つまり pytest から見ると 1 本のテストで、その中で device 側の検査が何件も走る形です。検査を増やしても、テストファイルは書き換えなくて済みます。後で出てくる「1 つの大きなテストにまとめる」と相性が良いのはこの形です。

Unity では各検査が junit のレポートにも記録されるので、`--junitxml` を使えば検査単位で結果が残ります。

どちらでもよく、混ぜても構いません。

## 実機でないと分からないこと

host core を使うと、sketch を PC のプログラムとして動かせます。速くて、ボードを繋がなくても動きます。ただし分かることは限られます。

| 対象 | host core で分かるか |
| --- | --- |
| 計算やパース、状態遷移などの純粋なロジック | 分かる |
| シリアルで交換するプロトコルの形 | 分かる |
| GPIO、I2C、SPI などの周辺機器 | 分からない |
| 実時間のタイミング、割り込み | 分からない |
| Flash や NVS の永続化 | 分からない |
| board 固有 API、Wi-Fi、BLE、USB | 分からない |

host core での実行は実機テストの代わりにはなりません。PC の OS や gcc の version、host core が提供する `Serial` の実装差で結果が変わることもあります。ロジックを速く回すための手段と考えてください。

### ユニットテストという考え方

ユニットテストは、部品を 1 つずつ切り離して確かめるテストです。関数 1 つ、クラス 1 つを対象にし、周りの事情を持ち込みません。対して、実機で全体を動かして確かめるテストは、部品の組み合わせを見ています。どちらにも役割があります。

| | 部品単位（ユニットテスト） | 組み合わせ（実機テスト） |
| --- | --- | --- |
| 対象 | 関数やクラス | sketch 全体とハードウェア |
| 速さ | 速い | 遅い。書き込みだけで時間がかかる |
| 必要なもの | なし。host core で足りる | ボード。台数の取り合いが起きる |
| 失敗したとき | 原因の範囲が狭い | 原因の範囲が広い |

配分の目安はこうです。**入力と出力で決まるもの、つまり計算、パース、状態遷移などは、host core のユニットテストに寄せます。** 周辺機器、タイミング、無線のように実機でしか分からないものだけを実機テストに残します。実機テストは遅く、使えるボードの数も限られるので、そこで確かめることを絞るほど全体が速くなります。

マイコンでは部品を切り離しにくいことがあります。ハードウェアを直接触るコードと、判断や計算をするコードが混ざっている場合です。この 2 つを分けておくと、後者は host core で回せます。テストしやすさを考えることが、そのまま設計の指針にもなります。

なお、ユニットテストは host core だけのものではありません。ボードの中で Unity や ArduTest を使って関数単位に確かめる形も、実機で動かすユニットテストです。周辺機器に依存する部品はこの形になります。

**どちらで回すかは選べます。** host core の利点は 2 つで、書き込みが要らないので速いことと、ボードが要らないことです。代わりに host core の platform を追加する手間がかかり、PC 側に C++ をビルドできる環境が必要になります。

**実機だけでユニットテストを回しても問題ありません。** 書き込みの時間はかかりますが、環境は普段の Arduino 開発と同じままです。まず実機で始めて、回す回数が増えて待ち時間が気になってきたら host core を足す、という順でも構いません。

## 何台のボードを使うか

台数によってできることが変わります。少ない台数から始めるのが良いです。

### 0 台: host core で動かす

host core を使うと、sketch を PC の gcc でビルドし、PC 上の実行ファイルとして起動します。シリアルポートの代わりに TCP socket で繋がります。

```yaml
# sketch.yaml
profiles:
  host:
    fqbn: lang-ship:host:host
    port: socket://localhost
    platforms:
      - platform: lang-ship:host (1.7.1)
        platform_index_url: https://tanakamasayuki.github.io/lang-ship-arduino-core/package_lang-ship_index.json

default_profile: host
```

ロジックの確認に向いています。ボードの取り合いも起きません。

**CI に乗せられることが大きな利点です。** GitHub Actions のような CI サービスには実機を繋げませんが、host core はボードを必要としないのでそのまま動きます。治具を自分で用意できない場合でも、ロジックのユニットテストだけは変更のたびに自動で確認できます。OSS の公開リポジトリなら無償の枠で回せるので、費用もかかりません。

実機テストは手元の環境か、自分で用意した self-hosted runner でしか動きません。だから host core で回せるものを host core に寄せておくほど、自動で確認される範囲が広がります。

### 1 台: 実機で動かす

いちばん基本の構成です。実機でのユニットテストに使います。

```bash
pytest tests/my_app --port=/dev/ttyUSB0
```

毎回 `--port` を書かずに済ませる方法は、peer の説明の後でまとめて扱います。

1 台でも、出力を自分の入力に配線して戻すループバックの形にすれば、送受信の両方を試せます。周辺機器、タイミング、永続化のように host core では分からないことは、ここから確かめられます。

### 2 台: 相手がいるテスト

通信の相手が必要なテストでは、sketch ディレクトリの直下に `peer_<name>/` を置きます。

```text
tests/
  my_app/
    my_app.ino
    sketch.yaml
    test_my_app.py
    peer_echo/
      peer_echo.ino
      sketch.yaml
```

テスト関数で `peers` を要求すると、peer も build、upload、接続されます。

```python
def test_round_trip(dut, peers):
    echo = peers["echo"]
    dut.write("send\n")
    echo.expect_exact("RECEIVED")
```

sketch は 2 つ書きます。primary は `send` を受けたら実際の通信手段で peer へ送り、peer は受け取ったら `RECEIVED` を出します。通信手段が BLE でも Wi-Fi でも I2C でも、テスト側の形は変わりません。

BLE や Wi-Fi のように相手が必要なものは当然 2 台要りますが、それ以外でも 2 台あったほうが楽なテストは多いです。相手側のログが直接読めるので、どちらが悪いのか切り分けられます。

### 3 台以上: クラスタ系のテスト

peer ディレクトリを増やすだけです。`peer_device` と `peer_device2` のように名前を分けます。

```text
    peer_device/
    peer_device2/
```

1 台の Central から 2 台の Peripheral へ同時接続する、中継役を挟む、といった構成が組めます。

台数が増えても仕組みは同じで、peer ディレクトリと port を増やすだけです。

このガイドでは、必要なボードが繋がっている前提で説明しています。実際には、いつも繋いである常設のボードと、そのときだけ繋ぐボードが混ざります。**port が解決できない peer があると、その peer を使うテストは自動で skip されます。** 失敗にはならないので、手元の台数が足りない環境でも、それ以外のテストは普通に流れます。

いつも繋がっているとは限らない機材を要求するテストの整理は、[上級者向けガイド](TESTING_ADVANCED.ja.md) で扱います。

## port の指定を `.env` にまとめる

`--port` を毎回書くのは面倒で、環境ごとに値も違います。`.env` ファイルに書いておけば省略できます。

```bash
# .env
TEST_SERIAL_PORT=/dev/ttyUSB0
```

```bash
uv run --env-file .env pytest tests/my_app
```

`--env-file` は pytest ではなく `uv` の option なので、**`pytest` より前に書きます**。`uv` を使わない場合は `export TEST_SERIAL_PORT=/dev/ttyUSB0` でも同じです。

`.env` は環境ごとの設定なので、**git には入れません**。このリポジトリでも `.gitignore` に入れてあります。共有したい場合は、値を伏せた `.env.example` を置いて、各自がコピーして使う形にします。

board を使い分けるなら、profile ごとに分けて書けます。変数名は profile 名を大文字にし、`-` を `_` に置き換えたものです。

```bash
# .env
TEST_SERIAL_PORT=/dev/ttyUSB0          # 既定
TEST_SERIAL_PORT_ESP32=/dev/ttyUSB0    # --profile esp32 のとき
TEST_SERIAL_PORT_UNO=/dev/ttyACM0      # --profile uno のとき
```

peer にも同じ仕組みがあります。`peer_echo` なら `TEST_SERIAL_PORT_PEER_ECHO` です。

```bash
# .env
TEST_SERIAL_PORT_PEER_ECHO=/dev/ttyUSB1
```

コマンドラインの `--port` を書いた場合は、そちらが `.env` より優先されます。普段は `.env` に置き、一時的に別の board を試すときだけ `--port` を付ける、という使い分けができます。詳しい優先順位は [上級者向けガイド](TESTING_ADVANCED.ja.md) にあります。

## session、module、test

ここから先は、テストを増やしたときに効いてくる話です。pytest の 3 つの用語を、この plugin での意味に対応させます。

| 用語 | 意味 | この plugin での役割 |
| --- | --- | --- |
| session | pytest を 1 回実行する全体 | 複数の sketch を順に扱う |
| module | テストファイル 1 つ | sketch の compile と upload の単位 |
| test | `def test_...` 関数 1 つ | シリアル接続を開いて閉じる単位 |

module は「テストファイル 1 つ」です。そのファイルが置かれたディレクトリにある `.ino` が、その module の sketch になります。

逆に、**`.ino` がないディレクトリのテストファイルには、この plugin は何もしません。** compile も upload も走らず、普通の pytest として動きます。ボードを使わないユニットテストは、`.ino` を置かないディレクトリにまとめてください。

```text
tests/
  unit/
    test_parser.py     <- .ino がない。plugin は何もしない
  my_app/
    my_app.ino
    sketch.yaml
    test_my_app.py     <- sketch ディレクトリのテスト
```

注意点が 1 つあります。**`.ino` があるディレクトリにテストを置くと、そのテストが `dut` を要求していなくても compile と upload が走ります。** compile と upload は module 単位の準備で、テストが接続するかどうかとは別に実行されるからです。ボードを使わないテストを sketch ディレクトリに混ぜると、無駄な待ち時間が増え、ボードも占有します。

各単位で起きることは次の通りです。

- **session の開始**: pytest が起動し、対象のテストを集めます。
- **module の開始**: sketch を compile し、ボードへ upload します。**upload でボードがリセットされます。** 物理ボードでは device lock を取得します。
- **test の開始**: シリアルポートを開きます。plugin はリセットのための操作を意図的には行いませんが、ポートを開くと DTR と RTS が立ちます。**これでボードがリセットされるかは board の回路によって変わります。**
- **test の終了**: シリアルポートを閉じます。
- **module の終了**: device lock を解放します。

ここから大事な結論が出ます。**upload では必ずボードがリセットされます。テストごとの接続でリセットされるかは board 次第です。** 前のテストが残した状態を次のテストがそのまま見る board もあり、接続のたびにリセットされて消える board もあります。DTR と RTS を EN に直結している board はリセットされ、自動リセット回路を挟んでいる board や native USB の board はされないことが多いです。

つまり同じ module に 2 本目のテストを書くと、そのテストが見るボードの状態は board の回路に依存します。**どちらにも依存しないテストを書くことが、唯一安全な方法です。**

## 基本は 1 つの module に 1 つのテスト

まずこの形を勧めます。

```text
tests/
  blink/
    blink.ino
    sketch.yaml
    test_blink.py      <- def test_blink(dut) が 1 つ
```

検証したいことが増えたときは、テストを増やす前に 2 つの方法を検討してください。

1. **1 つの大きなテストにまとめる。** コマンドを順に投げて応答を確認していく形なら、1 つのテストの中に何段でも書けます。
2. **sketch 自体を分割する。** 別の sketch ディレクトリにすれば module が分かれ、それぞれに upload が入るので、ボードの状態は必ずリセットされます。検証したい機能が別物なら、こちらが素直です。

## 複数のテストを書いてよい場合

書いてよいのは、**どのテストも単体で実行して通る**場合だけです。これをステートレスと呼びます。

`dut` にコマンドを投げて応答を確認するだけのテストは、前のテストに依存しないのでステートレスです。ただしその形なら、1 つの大きなテストの中で順に投げても同じことが実現できます。

分割に本当に価値があるのは、**非常に時間のかかるテストがあり、それだけを単体で実行したい**場合です。全体を流さずに 1 本だけ試せると開発が速くなります。

分割にはもう 1 つ利点があります。**失敗した場所が分かりやすい**ことです。5 段の検証を 1 つのテストに書くと、落ちたときにどの段かは出力を読んで判断します。5 本に分ければ、失敗したテストの名前がそのまま答えになります。

## 落とし穴: 前のテストに依存すると単体で動かない

この節では次の sketch を相手にします。`send` を受けるたびに数え、`count?` で数を答え、`reset` で 0 に戻します。

```cpp
// counter.ino
int sent = 0;

void setup()
{
  Serial.begin(115200);
}

void loop()
{
  if (Serial.available() == 0)
  {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();

  if (line == "reset")
  {
    sent = 0;
    Serial.println("RESET_OK");
  }
  else if (line == "send")
  {
    sent++;
    Serial.println("SENT");
  }
  else if (line == "count?")
  {
    Serial.print("COUNT ");
    Serial.println(sent);
  }
}
```

`sent` は upload でリセットされるまで残り続けます。ここが落とし穴の種です。

やってはいけない例です。

```python
# 悪い例
def test_send_first(dut):
    dut.write("send\n")
    dut.expect_exact("SENT")


def test_count(dut):
    dut.write("count?\n")
    dut.expect_exact("COUNT 1")     # test_send_first が動いた前提
```

`test_count` だけを実行するとカウントは 0 なので落ちます。順番を変えても落ちます。`test_send_first` が失敗しても落ちます。接続のたびにリセットされる board では、順番どおりに実行しても落ちます。どの board でも悪い例であることは変わりません。

直した例です。

```python
# 良い例
def test_send(dut):
    dut.write("reset\n")
    dut.expect_exact("RESET_OK")
    dut.write("send\n")
    dut.expect_exact("SENT")


def test_count(dut):
    dut.write("reset\n")
    dut.expect_exact("RESET_OK")
    dut.write("send\n")
    dut.expect_exact("SENT")
    dut.write("count?\n")
    dut.expect_exact("COUNT 1")
```

各テストが自分で必要な状態を作っています。どちらを単体で実行しても通ります。

**確認方法**は簡単です。テストを 1 本ずつ指定して実行し、全部通ればステートレスです。

```bash
pytest tests/my_app/test_my_app.py::test_count
```

CI では収集した nodeid を 1 つずつ回すと機械的に検証できます。

### 分割しても独立させたいとき

同じ sketch ディレクトリにテストファイルを 2 つ置くと、それぞれが別の module になります。module ごとに upload が走るので、ボードはその都度リセットされます。

```text
tests/
  my_app/
    my_app.ino
    sketch.yaml
    test_quick.py      <- module 1。upload される
    test_slow.py       <- module 2。もう一度 upload される
```

upload の時間が余分にかかりますが、状態の独立は保証されます。時間のかかるテストを切り出したいときに使えます。

## テストの最初は応答しない時間がある

upload の直後、ボードは起動して `setup()` を実行しています。この間はシリアルに送っても応答しません。ライブラリの初期化、Wi-Fi や BLE の起動、USB の列挙などがあり、待ち時間は環境によって変わります。

**固定時間の待ちは書かないでください。**

```python
# 悪い例
import time


def test_bad(dut):
    time.sleep(3)            # 3 秒で足りる保証がない
    dut.write("ping\n")
    dut.expect_exact("PONG")
```

3 秒では足りない環境では落ちます。1 秒で済む環境では毎回 3 秒を無駄にします。

代わりに、**実際に応答があるまで待つ**形にします。方法は 2 つあり、どちらを使うかは選べます。

### 方法 A: pytest から定期的に投げる

sketch に問い合わせコマンドを 1 つ用意し、応答が返るまで送り続けます。

```cpp
// polling.ino
void setup()
{
  Serial.begin(115200);
  delay(3000);                  // 初期化に 3 秒かかるとする
}

void loop()
{
  if (Serial.available() == 0)
  {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();

  if (line == "?")
  {
    Serial.println("READY");
  }
  else if (line == "ping")
  {
    Serial.println("PONG");
  }
}
```

準備できたかを記録する変数は要りません。**初期化中は `loop()` が動かないので、何を送っても読まれません。** `setup()` の中で Wi-Fi や BLE を起動する形なら、この性質がそのまま使えます。逆に、初期化を `loop()` の中で少しずつ進める作りにするなら、準備前にコマンドへ答えてしまわないよう自分で防ぐ必要があります。

```python
import pexpect
import pytest


def wait_ready(dut, attempts=20, interval=0.5):
    for _ in range(attempts):
        dut.write("?\n")
        try:
            dut.expect_exact("READY", timeout=interval)
            return
        except pexpect.TIMEOUT:
            continue
    pytest.fail("device did not become ready")


def test_with_polling(dut):
    wait_ready(dut)
    dut.write("ping\n")
    dut.expect_exact("PONG")
```

**なぜ 1 回送って長く待つのではなく、送り直すのか。** 早く送ったバイトは失われることがあるからです。

- native USB の board では、USB の列挙が終わる前に送ったバイトは届きません。
- 接続したときにリセットされる board では、リセット前に送ったものが消えます。
- 初期化中に送ったものは、シリアルの受信バッファに残っていれば初期化後に読まれますが、残っている保証はありません。

1 回だけ送って待つ形は、その 1 回が失われたときに何も救えません。届くまで送り直せば、いつ届くようになっても次の 1 回で応答が返ります。接続がいつ開いても動くので、実機で確実です。

### 方法 B: マイコンから準備完了を送る

sketch が `setup()` の最後に 1 行出し、pytest はそれを待ちます。

```cpp
// announce.ino
void setup()
{
  Serial.begin(115200);
  delay(3000);                  // 初期化に 3 秒かかるとする
  Serial.println("READY");
}

void loop()
{
  if (Serial.available() == 0)
  {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();

  if (line == "ping")
  {
    Serial.println("PONG");
  }
}
```

```python
def test_with_announcement(dut):
    dut.expect_exact("READY", timeout=10)
    dut.write("ping\n")
    dut.expect_exact("PONG")
```

書く量は少ないですが注意点があります。pytest がシリアルポートを開くのは upload の後なので、**それより前に出力された `READY` は取りこぼされることがあります**。

これは実際に起きます。2 台構成では、先に書き込みが終わった側が起動して出力している間、もう 1 台の書き込みが続いています。書き込みに数分かかる構成では、pytest が接続する頃には起動時の出力がすべて流れ終わっています。症状は**片側のログだけが完全に空になる**ことです。sketch の不具合ではなく、書き込みとリセットのタイミングの問題です。

host core の socket 接続では出力が保持されるので、この問題は起きにくいです。

実機で方法 B を使うなら、sketch 側で `READY` を繰り返し出すか、方法 A に寄せてください。「起きた瞬間に 1 度だけ知らせる」種類の状態も、問い合わせに対して現在の値を答えるようにしておくと、テスト側は通知を待たずに済みます。

## まとめ

- テストは、手で確認していた手順をコードに写したもの。sketch を書き込み、シリアルでやり取りし、期待した出力を確かめる。
- host core での実行はロジックの確認向け。周辺機器、タイミング、永続化、無線は実機でしか分からない。
- 台数は 0 台、1 台、2 台、3 台以上で、できることが変わる。peer は名前を増やすだけ。
- upload は module ごと、シリアル接続はテストごと。upload では必ずリセットされ、接続でリセットされるかは board 次第。
- 基本は 1 module に 1 テスト。増やしたいときは 1 つの大きなテストにまとめるか、sketch を分割する。
- 複数書くなら、どのテストも単体で通ること。前のテストに依存しない。
- 起動待ちは固定時間ではなく、応答があるまで待つ。

より進んだ話題は [上級者向けガイド](TESTING_ADVANCED.ja.md) にあります。
