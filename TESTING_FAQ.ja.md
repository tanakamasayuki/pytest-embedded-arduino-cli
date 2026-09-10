# よくある質問

[English](TESTING_FAQ.md)

症状から引くための索引です。各項目は、原因と、詳しく説明している節への案内だけを書いています。新しい内容はありません。ここで解決するなら、その先を読む必要はありません。

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

## ビルドと転送

### ハードウェアが要らないテストなのに、ビルドが走る

引き金は**同じディレクトリにある `.ino`** であって、テストが `dut` を要求したかどうかではありません。ハードウェア不要のテストは sketch の無いディレクトリに移してください。そうすればプラグインは何もしません。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *計画の階層*

### 昨日は通っていたのに、core やライブラリを上げたら通らなくなった

普段の実行を速くしているのは前回のビルドの再利用で、バージョンを上げたときはその再利用が裏目に出ます。`--clean` を付けて実行し直してください。**`--clean` が要るのは主にこの場面です。** リリース前に `--clean` 付きのフルテストを回しておく価値もあります。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *計画の階層*

### 転送に失敗する、または port を開けない

出方は 3 つあり、どれが出たかで見る場所が決まります。port を指定していなければ、接続の準備で `ValueError` になります。port は解決できるのに実体が無ければ、`arduino-cli upload` の中で失敗します。パスが存在しなければ、接続時に `FileNotFoundError` になります。`.env` に symlink を書いていると真ん中が起きやすくなります。**device が無くても文字列としては解決してしまう**からです。なお、これで primary が skip されることはありません。skip されるのは peer だけです。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *peer の board は plugin が面倒を見ます*

## device とのやりとり

### sketch が確かに print した行が、`expect` で取れない

`expect` は一致するところまで読み進み、**それより前を捨てます。** 先に別の一致があると、それより前に流れた行は後から expect できません。sketch 側では、起動時の出力を応答の前ではなく後に出してください。

→ [テストの応用](TESTING_ADVANCED.ja.md) の *expect の落とし穴*

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
