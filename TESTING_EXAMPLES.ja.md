# 実例集

[English](TESTING_EXAMPLES.md)

[テストの基本](TESTING_BASICS.ja.md) と [テストの応用](TESTING_ADVANCED.ja.md) で説明した内容が、実際に動いているプロジェクトです。`tests/` の下を読むと、ガイドの各項目がそのまま使われています。

規模や構成は変わっていくので、ここでは**何が見られるか**だけを書きます。

## まず読む

- **[examples/](examples/)** — このリポジトリに入っている最小例です。番号付きで並んでいて、1 つずつ独立しているので順に読めます。port の解決、環境変数から compile-time define を渡す形、NVS の永続と消去、build flag、Unity、ライブラリ構成と Arduino IDE 構成のレイアウトを扱います。**Unity を使った例はここにあります。**
- **[PCMFlowG722](https://github.com/tanakamasayuki/PCMFlowG722)** — 実プロジェクトの中でいちばん小さい形です。host core だけで動くので、ボードを持っていなくても読んで試せます。`tests/conftest.py` は sketch が書き出した `output/` を消すだけです。

## きれいな例

- **[TinyGFX](https://github.com/tanakamasayuki/TinyGFX)** — host core と ArduTest を組み合わせた構成です。`tests/` を機能ごとのディレクトリに分け、`tests/README` に方針を書き、人の操作が必要なテストは別ディレクトリに分けています。規模が増えても構成が保たれている例です。

## 複数台

- **[ESP32IRPulseKit](https://github.com/tanakamasayuki/ESP32IRPulseKit)** — 複数台の中でいちばんシンプルです。赤外線の送信と受信を 2 台で確認し、既存ライブラリとクロスチェックしています。`conftest.py` を使わず、標準機能だけで書かれています。`build_config.toml` の使い方も多く見られます。
- **[ESP32KeyBridge](https://github.com/tanakamasayuki/ESP32KeyBridge)** — 中規模の複数台構成です。`tests/` を `unit/`、`peer/`、`manual/`、`single/` に分け、`TEST_PLAN` に方針を書いています。こちらも `conftest.py` はありません。

## 人が操作するテスト

- **[PCMFlowUDP](https://github.com/tanakamasayuki/PCMFlowUDP)** — 音の確認は人が聞くのがいちばん確実です。そうしたテストを `manual/` に分けて、既定の実行から外しています。

## 大規模

- **[EspUsbDevice](https://github.com/tanakamasayuki/EspUsbDevice)** — 大きな構成の例です。2 通りのつなぎ方が同居しています。ESP32-S3 を 2 台使って peer 経由で確認するものと、ESP32-P4 を 1 台だけ使い、その 2 つの USB コントローラをケーブルで繋いで、ボードが自分自身をテストするものです。同じライブラリを別の構成で検証している例として読めます。`tests/conftest.py` では、シリアルログを検査して pytest の報告に足しています。

## 参考

- **[ArduTest](https://github.com/tanakamasayuki/ArduTest)** — device 側で判定するためのライブラリです。`arduino_test` fixture から使います。判定を device 側に置く手段の 1 つで、これがなくても構いません。Unity でもよく、素朴に sketch から結果を print して host 側で判定しても同じことができます。用途に合うなら便利、という位置付けです。
- **[host-arduino-core](https://github.com/tanakamasayuki/host-arduino-core)** — ガイドで **host core** と呼んでいるものの実体です。sketch を PC のプログラムとしてビルドし、シリアルポートの代わりに TCP socket で繋ぎます。実機なしでロジックを確認したいとき、CI で回したいときに使います。`tests/conftest.py` には、session 単位で platform を用意する autouse fixture の例もあります。
