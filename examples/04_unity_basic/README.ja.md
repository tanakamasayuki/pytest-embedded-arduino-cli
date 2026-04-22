# 04_unity_basic

このサンプルは、ESP32 向けの最小 Unity テスト sketch を示します。

- デフォルト profile は `esp32` です
- このサンプルは ESP32 系 target のみを対象にしています
- serial 経由の独自プロトコルではなく、Unity そのものの出力を確認する例です

同じ内容はテキストを `Serial.println(...)` で出し、Python 側で `dut.expect(...)` を使って検証することもできます。
ただし Unity を使うと、テスト結果の整形をフレームワーク側に任せられるため、Python 側のチェックをかなり簡略化できます。
このサンプルでも Python 側は `dut.expect_unity_test_output(...)` だけで検証できます。

ESP32 では Arduino の標準環境で `unity.h` を利用できるため、追加ライブラリなしでこの形を使えます。
一方で `uno` など他の環境では同じようには使えず、Unity を使いたい場合は別途組み込む必要があります。

実行例:

```bash
uv run pytest -s examples/04_unity_basic --port=/dev/ttyUSB0
```

sketch は起動時に 2 つの Unity テストケースを実行し、標準的な Unity のサマリを出力します。

実際の sketch は `unity_basic/` 配下にあります。
