# 02_env_define

このサンプルは、環境変数から compile-time define を渡す方法を示します。

- デフォルト profile は `esp32` です
- `esp32s3` を使う場合は `--profile` を明示します
- `uno` は Wi-Fi が使えないため skip される経路の例としてだけサポートします
- sketch の中身は Wi-Fi ですが、サンプルの主眼は `build_config.toml` です

このサンプルは `default_profile: esp32` を定義しているため、`--profile` なしでも動きます。

この方法は、Wi-Fi AP 名や API キーのように、環境ごとに異なる値を sketch に渡したいときに使います。

同じような値は `dut` 経由で serial 実行時に渡すこともできますが、その場合は sketch 側に受け取り処理が必要です。
また、serial 経由のやり取りは環境によっては結果が安定しないことがあるため、この plugin では compile-time define を使う方法も用意しています。

どちらを使っても構いません。
ただし、機密情報のように firmware へ埋め込むのがまずい値は、define ではなく `dut` 経由で実行時に渡してください。

実行前に環境変数を設定してください。

```bash
export TEST_WIFI_SSID=my-ssid
export TEST_WIFI_PASSWORD=my-password
uv run pytest examples/02_env_define --port /dev/ttyUSB0
```

同じ内容は `.env` ファイルから注入しても構いません。

```bash
uv run --env-file .env pytest examples/02_env_define
```

他の profile を使う例:

```bash
export TEST_SERIAL_PORT_ESP32S3=/dev/ttyUSB1
uv run pytest examples/02_env_define --profile esp32s3
```

profile ごとの環境変数名は、plugin と同じルールで profile 名を大文字化し、`-` を `_` に置換して作ります。

テンプレートは [`examples/.env.example`](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli/blob/main/examples/.env.example) にあります。
ただし場所が `examples/` 配下なので、編集前にリポジトリルートへ `.env` としてコピーしてください。

```bash
cp examples/.env.example .env
```

コピーしたあとは、利用する環境に合わせて `.env` の値を書き換えてください。

実際の sketch は `wifi_env_define/` 配下にあります。
