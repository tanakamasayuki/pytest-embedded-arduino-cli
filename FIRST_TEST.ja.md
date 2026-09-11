# 最初のテストを書く

[English](FIRST_TEST.md)

このページでは、実機1台を使う最初のテストを作り、compile、upload、serial通信までを一度通します。コマンドだけを確認したい場合は [READMEのクイックスタート](README.ja.md#クイックスタート) を使ってください。ここでは、各ファイルの意味とpytestが合否を決める仕組みまで説明します。

ボードが手元にない場合は、後半の [実機なしで試す](#実機なしで試す) から始められます。ただし host core は PC 上の代替環境です。この plugin の標準的な導入経路は実機です。

## 1. 前提を確認する

次のコマンドが使えることを確認します。

```bash
arduino-cli version
uv --version
```

この例では Arduino Uno を使います。board core は環境へ事前インストールしません。この後の `sketch.yaml` でplatformとversionを宣言し、Arduino CLIに解決させます。ESP32を使う場合も同様に、`esp32` profileと自分のboardに対応するportを選びます。

ローカルのpackage indexが古いと、`sketch.yaml` で指定した新しいcore versionが公開済みでも、Arduino CLIはそのversionを見つけられずエラーになります。初回実行前、core versionを更新したとき、またはversionが見つからないエラーが出たときはindexを更新してください。

```bash
arduino-cli core update-index
```

## 2. Python workspace を作る

Arduino projectのrootにPythonの依存関係、仮想環境、pytestの設定を直接置くと、Arduino側のファイルとテスト環境が混ざって分かりにくくなります。そのため、このガイドでは `tests/` を作り、その中にPython workspaceとテスト用sketchをまとめる構成を推奨します。

既存のArduino projectのrootで次を実行します。

```bash
mkdir tests
cd tests
uv init
uv add pytest-embedded-arduino-cli
```

これで `tests/` がPython側のworkspaceになり、plugin、`.venv`、`uv.lock`、pytestの設定をArduino project本体から分離して管理できます。

続けて `tests/.gitignore` を作り、ローカル環境、build結果、テスト実行時の生成物をGitの対象から外します。

```gitignore
# Python environment and caches
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/

# Local settings and generated test results
.env
.pytest-results/
.pytest-embedded/
ardutest/

# Arduino CLI build output under each test sketch
**/build/
```

`.env` にはserial portやcredentialなどmachine固有の値が入るためcommitしません。共有する変数名や記入例が必要なら、実際の値を含まない `.env.example` をcommitします。

一方、`pyproject.toml`、`uv.lock`、`.python-version`、`sketch.yaml`、`.ino` / `.h` / `.cpp`、`test_*.py` は基本的にcommitします。特にこのガイドのように特定projectのCI環境を再現するtest workspaceでは、Python依存を固定する `uv.lock` もcommitすることを推奨します。除外項目の理由と運用上の例外は、[FAQ: Gitには何をcommitし、何を除外すればよいか](TESTING_FAQ.ja.md#gitには何をcommitし何を除外すればよいか)を参照してください。

追加前にGitからどう見えているかも確認できます。`--no-index`を付けると、まだ存在しないbuild directoryもpatternだけで確認できます。

```bash
git status --short
git check-ignore -v --no-index .env hello/build/
```

`.env`と`hello/build/`には、どの`.gitignore` ruleで除外されたかが表示されます。一方、`uv.lock`や`sketch.yaml`は除外されず、`git status`の追加対象に現れることを確認してください。

## 3. Arduino sketch を作る

続けて `tests/` の中でArduino CLIにsketchを作らせます。

```bash
arduino-cli sketch new hello
cd hello
touch sketch.yaml
touch test_hello.py
```

`arduino-cli sketch new hello` がArduino IDEと同じ形の `hello/hello.ino` を作ります。そこへplugin用の `sketch.yaml` とpytestの `test_hello.py` を追加します。

関係するファイルは次の配置になります。

```text
tests/
  .gitignore
  pyproject.toml
  uv.lock
  hello/
    hello.ino
    sketch.yaml
    test_hello.py
```

Arduino IDEのprojectと同じように、sketchディレクトリには主となる `.ino` を1つ置き、補助コードは `.h` / `.cpp` に分けます。テストファイルもそのディレクトリに置きます。

## 4. sketch とprofileを書く

Arduino CLIが作った `hello.ino` を、pytestから `ping` が届いたら `PONG` を返すsketchに書き換えます。

```cpp
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

同じディレクトリの `sketch.yaml` に、使用するboard profileを書きます。

```yaml
profiles:
  uno:
    fqbn: arduino:avr:uno
    platforms:
      - platform: arduino:avr (1.8.8)

  esp32:
    fqbn: esp32:esp32:esp32
    platforms:
      - platform: esp32:esp32 (3.3.11)
        platform_index_url: https://espressif.github.io/arduino-esp32/package_esp32_index.json

default_profile: uno
```

実際のprojectでは、`fqbn` とcoreのversionを使用するboardに合わせてください。

接続したboardの候補は `arduino-cli board list`、package indexに登録されたboardの検索は `arduino-cli board search` で確認できます。たとえばUnoを検索すると、board名、FQBN、platform IDが表示されます。

```bash
arduino-cli board list
arduino-cli board search "Arduino Uno"
```

検索結果のFQBNをprofileの `fqbn` に、Platform IDとversionを `platforms` に書きます。`uno` や `esp32` というprofile名はproject内で決める名前であり、FQBNそのものではありません。`arduino-cli board listall` は導入済みplatformが提供するboardだけを列挙するcommandなので、coreを事前導入しないこの構成でFQBNを探す用途には `board search` を使います。

### coreのversionは必ず指定する

`platform` は `arduino:avr (1.8.8)` のように、core名とversionを組み合わせて書きます。**versionは省略せず、必ず指定してください。**

versionを省略すると、その環境に事前導入されているcoreが使われます。この場合、実際にどのversionでbuildしたかを `sketch.yaml` から特定できません。また、環境にcoreが入っていなければbuildはエラーになります。versionを固定しておけば、Arduino CLIが宣言されたversionを解決し、別のmachineやCIでも同じ条件を再現できます。

`platform_index_url` はArduino IDEでいうBoard ManagerのURLです。Arduino CLIの標準indexにないplatformなど、追加のBoard Manager URLが必要なcoreでは、profile内に指定することを推奨します。上のESP32 profileがその例です。

どのversionに固定するかはprojectの目的で決めます。

- **build済みbinaryを配布するproject**: 実際に製品をbuildするversionに固定します。テストと配布binaryの条件を一致させることを優先します。
- **source fileで配布するproject**: 利用者が新しい環境でbuildする可能性が高いため、なるべく最新のcore versionへ追従します。更新時はテストを通し、対応versionを更新します。

「versionを固定すること」と「古いversionを使い続けること」は別です。固定した値を、projectの方針に従って意図的に更新してください。

## 5. pytest のテストを書く

同じディレクトリの `test_hello.py` に、host側の操作と合否判定を書きます。

pytestは、既定では名前が `test_` で始まるPythonファイルを探し、その中にある `test_` で始まる関数をテストとして実行します。そのため、ファイルを `test_hello.py`、関数を `test_ping` としています。`main()` を書いたり、関数を自分で呼び出したりする必要はありません。

テスト関数の引数にある `dut` は、このpluginとpytest-embeddedが用意するfixtureです。利用者が `dut` objectを作る必要はありません。pytestがテストを実行する前に、選択したprofileでsketchをcompile・uploadし、serial portへ接続したDUTをこの引数へ渡します。

### 起動直後のserial通信をそのままテストしない

boardによっては、起動直後にはまだserial通信を受け取れません。uploadやserial portへの接続が完了していても、boardのreset、USB serialの再接続、bootloaderの実行、sketchの初期化が続いている場合があります。つまり、**hostがserial portを開けたことと、sketchがテキストを送受信できることは同じではありません。**

この時間にhostから送った文字列は、sketchへ届かず失われることがあります。反対に、sketchが起動直後に一度だけ出力した文字列も、host側の接続が間に合わなければ受け取れません。そのため、次のような起動直後の1回だけの通信を前提にすると、sketchが正常でもテストが失敗する可能性があります。

- hostが一度だけcommandを送り、その応答を待つ
- sketchが `setup()` で一度だけ出力する起動メッセージを待つ
- boardごとに異なる起動時間を、短い固定時間で待つ

この例では、その取りこぼしを避けるためにPING/PONG方式のreadiness handshakeを使います。hostは短い間隔で `ping` を送り直し、sketchが受信できる状態になった後で `PONG` を返した時点を「通信の準備完了」とします。起動直後のどの1回が届くかには依存せず、実際に双方向通信できたことを確認してからpassできます。

```python
import time

import pexpect
import pytest


STARTUP_TIMEOUT = 20.0
PROBE_INTERVAL = 0.5


def test_ping(dut):
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        dut.write("ping\n")
        try:
            dut.expect_exact("PONG", timeout=min(PROBE_INTERVAL, remaining))
            return
        except pexpect.TIMEOUT:
            continue
    pytest.fail(f"device did not answer PONG within {STARTUP_TIMEOUT} seconds")
```

最初の `ping` がboardへ届かなければ、対応する `PONG` も返らないため、最初の `dut.expect_exact(...)` はtimeoutします。これは起動中には想定した動作です。1回の待機は `PROBE_INTERVAL` の0.5秒で区切り、直後の `except` がtimeoutを捕まえます。そのためpytestのテスト全体はまだfailせず、次の `ping` を送れます。

再試行全体は `STARTUP_TIMEOUT` の20秒で打ち切ります。この値には2つの役割があります。正常な環境で起こる起動のばらつきを許すことと、deviceが本当に停止している場合にテストを有限時間でfailさせることです。

短すぎると、環境が遅いだけの正常なboardをfailにします。一方、長くしすぎると、本当の故障や配線ミスを検出するまで毎回待たされます。多くのboardは数秒で応答し、起動が遅い環境でも20秒程度をひとつの目安にできます。そのうえで、**最も遅い正常環境で実測した起動時間に余裕を足し、それでも異常時に待てる長さ**を選んでください。20秒はこの導入例の初期値であり、すべてのprojectに対する正解ではありません。

起動時間そのものを性能要件として検査したい場合は、このhandshakeと分けます。まず寛容な上限で「起動して応答できること」を確認し、別のテストで計測値をassertしてください。起動確認のtimeoutを厳しくすると、機能停止と単なる性能低下を区別できなくなります。

各部分の役割は次のとおりです。

| コード | 役割 |
| --- | --- |
| `import pexpect` | serial出力が時間内に届かなかったことを表す `pexpect.TIMEOUT` を使います。pluginの依存に含まれるため、別途追加する必要はありません。 |
| `import pytest` | 最後まで応答がなかったとき、`pytest.fail(...)` で理由を付けて失敗させます。 |
| `import time` | system clockの変更に影響されない `time.monotonic()` で、再試行全体の期限を測ります。 |
| `STARTUP_TIMEOUT` | 起動完了を待つ全体の上限です。projectと実行環境に合わせて調整します。 |
| `PROBE_INTERVAL` | 1回の応答待ちと、問い合わせを送り直す間隔です。 |
| `def test_ping(dut)` | pytestが収集するテスト関数です。接続済みのDUTを `dut` fixtureとして受け取ります。 |
| `dut.write("ping\n")` | hostからdeviceへ文字列を送ります。sketchが `readStringUntil('\n')` で1行を読むため、末尾の改行も必要です。 |
| `dut.expect_exact(...)` | deviceから大文字小文字まで同じ `PONG` が届くのを、`PROBE_INTERVAL` または全体の残り時間の短い方まで待ちます。 |
| `except pexpect.TIMEOUT` | 1回の応答待ちがtimeoutした場合です。例外をここで捕まえるので、テスト全体はfailせず、期限まで `ping` を送り直します。 |
| `return` | `PONG` を確認できたのでテスト関数を終了します。例外や `pytest.fail` がなければ、そのテストはpassです。 |
| `pytest.fail(...)` | 全体の期限まで応答がなかった場合に、待った秒数を含む理由でテストをfailにします。 |

実行時には次の順に進みます。

1. pytestが `test_hello.py` と `test_ping` を見つけます。
2. pluginが `sketch.yaml` のprofileを使ってcompile・uploadします。
3. serial portへ接続し、`dut` をテスト関数へ渡します。
4. テストが `ping` を送り、0.5秒だけ `PONG` を待ちます。
5. 応答がなければ送り直し、応答があればpassします。
6. `STARTUP_TIMEOUT` の期限まで応答がなければ、メッセージ付きでfailします。

`time.sleep(3)` のような固定待ちは、遅い環境では不足し、速い環境では無駄になります。この例は実際に応答が返るまで短い間隔で問い合わせるため、boardの起動時間が変わっても同じテストを使えます。

`expect_exact` は「その文字列が出力されること」を合否条件にします。数値を比較する、複数行を順に確認する、正規表現で値を取り出す、といった書き方は [テストの基本](TESTING_BASICS.ja.md) と [テストの応用](TESTING_ADVANCED.ja.md#expect-の落とし穴) で扱います。

## 6. port を確認して実行する

1つ上のPython workspaceへ戻り、Arduino CLIで接続中のboardとportを確認します。

```bash
cd ..
arduino-cli board list
```

Linuxでは、同じboardを再接続しても名前が安定しやすい `/dev/serial/by-id/` も確認できます。

```bash
ls -l /dev/serial/by-id/
```

該当するentryがある場合は、`/dev/ttyACM0`などの代わりにそのpathを `--port=` へ指定できます。ただし、bootloaderとsketch実行時でUSBのidentity自体が変わるboardでは、別のentryになることがあります。

Uno の例:

```bash
uv run pytest hello --profile=uno --port=/dev/ttyACM0
```

ESP32 の例:

```bash
uv run pytest hello --profile=esp32 --port=/dev/ttyUSB0
```

Windows では port を `COM3` などに置き換えます。成功すると、最後に `1 passed` と表示されます。

毎回 port を書かない方法は、[テストの基本: port の指定を `.env` にまとめる](TESTING_BASICS.ja.md#port-の指定を-env-にまとめる) で説明しています。

## うまくいかないとき

まず `-s` と `-v` を付けて再実行すると、どの段階で止まっているかを確認しやすくなります。

```bash
uv run pytest hello --profile=uno --port=/dev/ttyACM0 -s -v
```

- `-s`: boardから受信したserial出力を、テストの実行中にconsoleへ表示します。表示と並行してserial logの収集も続き、`dut.log`にも保存されます。sketchがどこまで起動したか、期待していた文字列が実際にはどう出力されたかをその場で確認するときに使います。
- `-v`: 収集したtest名に加え、pluginが実行する `arduino-cli compile` / `arduino-cli upload` のcommandを表示します。さらに詳しい `cwd`、sketch directory、build path、profile、portまで確認する場合は `-vv` を使います。

`-s` と `-v` は役割が異なるため、組み合わせて使えます。serial通信をその場で見るなら `-s`、compile・uploadや設定の解決を調べるなら `-v` または `-vv` が中心になります。`-s` を付けなくてもserial logは収集されるため、通常実行では外し、問題を調べるときだけ付けても構いません。

保存されたlogは、Linuxでは通常 `/tmp/pytest-embedded/<実行日時>/<テスト名>/dut.log` にあります。ただしrootはOSや一時directoryの設定によって変わります。保存場所、`-s`との違い、任意のdirectoryへ固定する方法は、[FAQ: serial出力を実行中に見たい、あとからlogも確認したい](TESTING_FAQ.ja.md#serial出力を実行中に見たいあとからlogも確認したい)を参照してください。

- `arduino-cli` が見つからない: Arduino CLI をインストールし、`PATH` に追加します。
- platform や version が見つからない: package indexを更新し、`sketch.yaml` のplatform名、index URL、versionを確認します。coreを環境へ手動インストールして回避しないでください。
- upload できない: `arduino-cli board list` で port を確認し、Arduino IDE の serial monitor など、同じ port を開いているプログラムを閉じます。
- Linuxで `Permission denied` になる: [FAQ: Linuxでserial portを開くとPermission deniedになる](TESTING_FAQ.ja.md#linuxでserial-portを開くとpermission-deniedになる)を確認します。
- upload後にport名が変わる: [FAQ: upload後にserial portの名前が変わり、接続できない](TESTING_FAQ.ja.md#upload後にserial-portの名前が変わり接続できない)を確認します。
- 出力が文字化けする: `Serial.begin(115200)` と pytest の baud rate を合わせます。既定は 115200 です。
- それ以外: [よくある質問](TESTING_FAQ.ja.md) を症状から探してください。

## 実機なしで試す

host core を使うと、sketch を PC 用の実行ファイルとして build し、serial port の代わりに TCP socket で接続できます。ボードは不要ですが、host machineに `gcc` / `g++` 互換のC/C++ toolchainが必要で、実機固有の動作は検査できません。host coreのpackageにはcompilerやlinkerが含まれないため、これらはOS側へ事前に導入します。

Debian / Ubuntu系のLinuxでtoolchainが未導入なら、次のpackageを導入します。ほかのOSを含む詳しい手順は、[host-arduino-core: 事前準備](https://github.com/tanakamasayuki/host-arduino-core/blob/main/README.ja.md#事前準備)を参照してください。

```bash
sudo apt update
sudo apt install build-essential
gcc --version
g++ --version
```

host coreのサンプルは、このページで作ったArduino projectではなく、`pytest-embedded-arduino-cli` repositoryの `examples/09_host_arduino_core` に含まれています。Linuxで `/tmp` に新しくcloneして試す場合は、次のように実行します。

```bash
cd /tmp
git clone https://github.com/tanakamasayuki/pytest-embedded-arduino-cli.git
cd pytest-embedded-arduino-cli
uv run pytest examples/09_host_arduino_core --profile=host -s -v
```

`uv run`がrepositoryの設定から必要なPython環境を用意するため、事前の `uv sync` は不要です。すでに別の場所へcloneしている場合は、`cd /tmp` と `git clone` の代わりに、そのrepositoryのrootへ移動して同じ `uv run pytest ...` を実行してください。

設定と制約は [`examples/09_host_arduino_core`](examples/09_host_arduino_core/README.ja.md) を参照してください。

## 次に読む

- [テストの基本](TESTING_BASICS.ja.md): module、test、実機、host core、peer の考え方
- [examples](examples/README.ja.md): 目的別に選べる実行可能なサンプル
- [README](README.ja.md): option と設定のリファレンス
- [よくある質問](TESTING_FAQ.ja.md): エラーや不安定なテストの調べ方
- [GitHub Actionsではどのテストを実行すればよいか](TESTING_FAQ.ja.md#github-actionsではどのテストを実行すればよいか): pure unit test、host core、profile別build testの分け方
