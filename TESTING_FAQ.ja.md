# よくある質問

[English](TESTING_FAQ.md)

症状や疑問から引くための索引です。各項目に短い回答を書き、必要に応じて詳しいguideへ案内します。ここで解決するなら、その先を読む必要はありません。

## 収集と起動

### `import file mismatch` が出て、テストが 1 つも走らない

同じ basename のテストファイルが 2 つあります。pytest はテストモジュールを basename で import するので、2 つ目が 1 つ目とぶつかります。**basename はプロジェクト全体で一意にしてください。** ディレクトリが違っても、同時に実行されることがなくても同じです。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *テストの収集規則*

### テストが拾われない、または fixture が動いていないように見える

テスト関数には `test_` の接頭辞が要ります。逆方向の落とし穴もあります。**名前が `test_` で始まる fixture は fixture としては普通に働きますが、pytest が警告なく収集から外します。** そのため、何も起きていないように見えます。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *テストの収集規則*

### `PluginValidationError: unknown hook` が出て pytest が起動しない

`conftest.py` の `pytest_*` 関数の名前が間違っています。フック名は決まっていて、知らない名前を黙って無視するのではなく、起動を拒否します。pytest-embedded もこのプラグインも独自のフック名を追加していません。**フック名は pytest のものだけです。**

→ [テストの応用](TESTING_ADVANCED.ja.md) の *conftest.py とは*

### すべてのテストで `record_xml_attribute` の警告が出る

`PytestExperimentalApiWarning: record_xml_attribute is an experimental feature` が、テストごとに 1 回ずつ出ます。行番号が自分のテスト関数を指すので紛らわしいのですが、**原因は自分のテストではありません。** pytest-embedded の `app_path` fixture が pytest の `record_xml_attribute` を要求していて、pytest 側がその API を experimental として扱っているためです。直すところは無いので、黙らせてください。

```toml
# pyproject.toml
[tool.pytest.ini_options]
filterwarnings = [
    "ignore:record_xml_attribute is an experimental feature:pytest.PytestExperimentalApiWarning",
]
```

同じ設定を `pytest.ini` に書く場合は、角括弧と引用符の無い改行区切りの並びになります。

```ini
# pytest.ini
[pytest]
filterwarnings =
    ignore:record_xml_attribute is an experimental feature:pytest.PytestExperimentalApiWarning
```

→ [テストの応用](TESTING_ADVANCED.ja.md) の *設定ファイル: pytest.ini と pyproject.toml*

## project fileとGit

### Gitには何をcommitし、何を除外すればよいか

テストを同じ条件で再現するために必要な入力はcommitし、machine固有の設定と再生成できる出力は除外します。

**基本的にcommitするもの:**

- `pyproject.toml`: Pythonの直接依存とpytest設定
- `uv.lock`: 解決済みのPython依存version
- `.python-version`: projectでPython versionを揃える場合
- `sketch.yaml`: board、core、libraryのversionとprofile
- `.ino`、`.h`、`.cpp`、`test_*.py`: sketchとテスト本体
- `.env.example`: secretや実際のportを含まない設定例

**基本的に`.gitignore`へ追加するもの:**

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.env
.pytest-results/
.pytest-embedded/
ardutest/
**/build/
```

`**/build/` はArduino CLIのcompile結果で、profileごとに再生成できます。`.pytest-results/` は `--save-state` の状態、`.pytest-embedded/` は `--root-logdir=.pytest-embedded` とした場合のserial log、`ardutest/` はArduTestのartifactです。既定のserial logがsystemの一時directoryにある場合はrepository外なので、Gitの除外対象には現れません。

特定projectのCIを再現するtest workspaceでは、`uv.lock`をcommitすることを推奨します。一方、libraryとして複数versionのPython依存との互換性を意図的に検査する場合は、lockを使わないjobも別に用意できます。lockを除外するだけで目的が達成されるわけではないため、通常の再現テストと依存範囲の互換性テストを分けてください。

`.env` は実際のserial portだけでなく、Wi-Fi credentialなどを含む可能性があります。実値はcommitせず、必要な変数名だけを `.env.example` で共有してください。すでに追跡されているfileは `.gitignore` へ追加しただけでは追跡解除されないため、secretをcommitしていた場合はrepositoryの履歴とcredential自体の交換も確認が必要です。

→ [最初のテスト](FIRST_TEST.ja.md#2-python-workspace-を作る) の `.gitignore` 例

## ビルドと転送

### `sketch.yaml not found` または `multiple .ino files found` が出る

テストファイルを置いたディレクトリがsketchディレクトリです。Arduino IDEのprojectと同じように、主となる `.ino` を1つ置き、同じ場所か上位ディレクトリに `sketch.yaml` を置いてください。補助コードは `.h` / `.cpp` に分けます。

→ [テストの基本](TESTING_BASICS.ja.md) の *ディレクトリ構成*

### profileを選ぶように言われる、または指定したprofileがskipされる

primary profileは `--profile`、`default_profile`、profileが1つだけの場合の自動選択、の順で決まります。複数あるのにどれも選ばれていなければエラーです。指定したprofileがそのsketchの `sketch.yaml` に無ければ、非対応の組み合わせとしてbuild前にskipされます。

peerはprofileが1つだけでも自動選択しません。`peer_<name>/sketch.yaml` に `default_profile` を書くか、`--peer-profile <name>:<profile>` を指定してください。

→ [README](README.ja.md) の *peer DUT*

### `--run-mode=build` で全テストがskipと表示される

正常です。build modeはsketchをcompileしますが、pytestのtest関数は実行しないため、test itemは `skipped test execution in build-only mode` として報告されます。compileが失敗していなければ、buildの目的は達成されています。

→ [README](README.ja.md) の *使い方*

### `--run-mode=test` で build output directory が見つからない

test modeはcompileを省略し、同じsketch・同じprofileの既存buildを使います。先に `--run-mode=all` または `--run-mode=build` でbuildしてください。profileを切り替えた場合はbuild directoryも別になります。

→ [README](README.ja.md) の *使い方*

### ハードウェアが要らないテストなのに、ビルドが走る

引き金は**同じディレクトリにある `.ino`** であって、テストが `dut` を要求したかどうかではありません。ハードウェア不要のテストは sketch の無いディレクトリに移してください。そうすればプラグインは何もしません。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *計画の階層*

### 昨日は通っていたのに、core やライブラリを上げたら通らなくなった

まずエラーを分けます。指定したversionが見つからない場合は、ローカルのpackage/library indexが古い可能性があるため、`arduino-cli core update-index` と `arduino-cli lib update-index` を実行します。versionは解決できるのにcompileが失敗する場合は、前回のbuild再利用が裏目に出ている可能性があるため、`--clean` を付けて実行し直してください。リリース前にindexを更新し、`--clean` 付きのフルテストを回しておく価値もあります。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *計画の階層*

### ローカルでは通るのに、GitHub ActionsやDockerで新しいcore versionが見つからない

CIがArduino CLIのdata directoryやDocker imageを使い回すと、保存されているpackage indexも古いまま残ります。`sketch.yaml` を新しいcore versionへ更新しても、古いindexはそのversionの存在を知らないため、platformを解決できずbuildが失敗します。

cacheを復元した**後**、pytestやbuildを始める**前**にindexを更新してください。library versionも更新する可能性があるjobでは、library indexも同時に更新します。

```yaml
- name: Update Arduino indexes
  run: |
    arduino-cli core update-index
    arduino-cli lib update-index

- name: Run build tests
  run: uv run pytest examples/01_basic --profile=uno --run-mode=build
```

Dockerfileのimage build時に一度だけ `core update-index` を実行しても、古いimageを継続利用すればindexも古いままです。jobまたはcontainerの開始後に更新するか、base imageを更新する運用を用意してください。core本体のcacheは再利用して構いませんが、**cacheがあることとindexが新しいことは別です。**

→ [テストの応用](TESTING_ADVANCED.ja.md) の *ビルドテストは和ではなく積で増える*

### 転送に失敗する、または port を開けない

出方は 3 つあり、どれが出たかで見る場所が決まります。port を指定していなければ、接続の準備で `ValueError` になります。port は解決できるのに実体が無ければ、`arduino-cli upload` の中で失敗します。パスが存在しなければ、接続時に `FileNotFoundError` になります。`.env` に symlink を書いていると真ん中が起きやすくなります。**device が無くても文字列としては解決してしまう**からです。なお、これで primary が skip されることはありません。skip されるのは peer だけです。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *peer の board は plugin が面倒を見ます*

### compile後、uploadの前で長く待つ

同じ物理deviceを使う別のpytest processがdevice lockを保持している可能性があります。既定では最大300秒待ちます。並行実行中のpytestを確認し、必要なら `--device-lock-timeout` を調整してください。lock fileが残っているだけではlock中になりません。OSのfile lockはprocess終了時に解放されます。

→ [README](README.ja.md) の *主な option*

## device とのやりとり

### シリアル出力が文字化けする

sketchの `Serial.begin(...)` とpytestのbaud rateが一致していません。このpluginの既定は115200です。sketch側を合わせるか、`--baud` を指定してください。

→ [テストの基本](TESTING_BASICS.ja.md) の *どういう仕組みで動くか*

### sketch が確かに print した行が、`expect` で取れない

`expect` は一致するところまで読み進み、**それより前を捨てます。** 先に別の一致があると、それより前に流れた行は後から expect できません。sketch 側では、起動時の出力を応答の前ではなく後に出してください。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *expect の落とし穴*

### `READY` を出しているのに最初の `expect` がtimeoutする

pytestがserial portを開く前に、起動時の `READY` が流れ終わった可能性があります。特にpeerを含む構成では、もう一方をuploadしている間に先のdeviceが出力します。起動時に一度だけ通知するのではなく、pytestから準備状態を問い合わせて、応答があるまで送り直すhandshakeにしてください。

→ [テストの基本](TESTING_BASICS.ja.md) の *テストの最初は応答しない時間がある*

### serial出力を実行中に見たい、あとからlogも確認したい

`-s` を付けると、boardから受信したserial出力を実行中のconsoleで確認できます。

```bash
uv run pytest tests/my_app --profile=uno --port=/dev/ttyACM0 -s
```

`-s` はライブ表示のためのoptionです。付けた場合もserial logは収集され、`dut.log`へ保存されます。`-s` を付けない通常実行でも、consoleに表示されないだけでserial logの収集と保存は行われます。

既定の保存先rootは、systemの一時directory内にある `pytest-embedded/` です。Linuxでは通常、次のような配置になります。

```text
/tmp/pytest-embedded/<実行日時>/<テスト名>/dut.log
```

一時directoryはOSや `TMPDIR`、`TEMP`、`TMP` などの環境設定で変わるため、常に `/tmp` とは限りません。保存先を分かりやすい場所へ固定したい場合は、`--root-logdir` を指定します。

```bash
uv run pytest tests/my_app --root-logdir=.pytest-embedded
```

詳しい保存内容とOSごとの場所は、次も参照してください。

- [README: log directory の結果 summary](README.ja.md#log-directory-の結果-summary)
- [テストの応用: ログとアーティファクトの置き場所](TESTING_ADVANCED.ja.md#ログとアーティファクトの置き場所)

### `dut.log` の末尾が無い、または行の途中で切れる

最後に一致した時点でテストが終わると、それより後の受信がlogへ届く前に接続が閉じることがあります。deviceに終端markerを出させてそこまで `expect` するか、最後に `pexpect.TIMEOUT` を待って残りをdrainしてください。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *ログとアーティファクトの置き場所*

### 正規表現で受け取った値が途中までしかない

末尾の可変長patternが、1行の残りが届く前にmatchしています。captureの後を `\r?\n` などの行末まで含め、完全な行が届いてから確定させてください。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *末尾の可変長フィールドは行末で止める*

### host core で、module の 2 本目のテストが接続できない

接続を閉じると実行ファイルが終了するので、繋ぐ先が残っていません。`parametrize` も同じ理由で失敗します。**host core では 1 module 1 テストです。** テストではなく module を分けてください。書き込みの待ち時間もボードの取り合いも無いので、host core では module を増やす費用は小さめです。

→ [テストの基本](TESTING_BASICS.ja.md) の *0 台: host core で動かす*

### 書き込んだのに、前回の状態が残っている

不揮発領域が upload で消えるかは **board 次第**で、既定では消えないことが多いです。テストの開始時に sketch 側で消すか、platform に全消去の設定があればそれを使ってください。全消去はどの platform にもあるわけではなく、指定の仕方も platform ごとに違います。

→ [テストの基本](TESTING_BASICS.ja.md) の *session、module、test*

### 実行が終わってもアドバタイズやピンの出力が続く

止める処理を書かない限り止まりません。早期終了でも走るように、止める処理は fixture に置いてください。**リセットすればきれいになるとは限りません。** ソフトウェアリセットがどこまで初期化するかは board 次第で、届くのはリセット信号が届く範囲までであり、しかも `setup()` が走り直して状態を作り直してしまうことがあります。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *中断時の後片付け*

## テスト計画

### 単独では通るのに全体で落ちる、またはその逆

**どちらも毎回同じ結果になるなら**、前のテストがしたことに依存しています。よくあるのは 3 つで、積み上がった状態への相乗り、最初に走ることへの依存、他のテストが汚す状態をきれいな前提で assert すること、です。**順序ではなく依存を直してください。** 順序を固定するのは、設計の誤りを消すのではなく隠すだけです。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *うまくいかない 3 つの形*

### 同じテストが通ったり落ちたりする

**探し始める前に 3 つの形を切り分けてください。** 何も変えずに同じ選択で 2 回流します。**食い違えば本当のレース**です。固定の待ち時間、1 度だけ通知されるものを待っている、時間切れした `expect` の後のチェック、失敗を塗り潰している retry などが原因になります。**一致すれば決定的**で、実行内の順序依存か、**前回の実行が残した状態**のどちらかです。後者は単独でも逆順でも再現せず、**運んでくるのは peer が最も多いです。** ペアリング情報は upload を越えて残り、そもそも誰もリセットしない device が peer のこともあります。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *通ったり落ちたりするテスト*

### 頼んでいないのに peer のテストが skip される

port や profile を解決できない peer は、理由付きで skip されます。これは意図した動作です。同じテストファイルが、その board があるベンチでも、無いベンチでも動くようにするためです。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *peer の board は plugin が面倒を見ます*
