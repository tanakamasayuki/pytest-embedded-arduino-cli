# 01_basic

最初に試すための最小サンプルです。

- デフォルト profile は `esp32` です
- `uno` のような他の target を使いたい場合は `--profile` を明示して切り替えます
- 実際の sketch は `basic/` 配下に置いています

このサンプルは `default_profile: esp32` を定義しているため、`--profile` なしでも動きます。

実行例:

```bash
uv run pytest examples/01_basic --port=/dev/ttyUSB0
```

sketch を直接指定しても構いません。

```bash
uv run pytest examples/01_basic/basic --port=/dev/ttyUSB0
```

他の profile を使う例:

```bash
uv run pytest examples/01_basic --profile uno --port=/dev/ttyACM0
```

このサンプルでは、環境変数から serial port を解決する方法も確認できます。

- 共通の既定値には `TEST_SERIAL_PORT` を使います
- profile ごとの値には `TEST_SERIAL_PORT_<PROFILE>` を使います
- profile ごとの環境変数名は、profile 名を大文字化して `-` を `_` に置換して作られます

例:

```bash
export TEST_SERIAL_PORT=/dev/ttyUSB0
uv run pytest examples/01_basic
```

```bash
export TEST_SERIAL_PORT_UNO=/dev/ttyACM0
uv run pytest examples/01_basic --profile uno
```

たとえば `esp32-s3` は `TEST_SERIAL_PORT_ESP32_S3` になります。

`.env` ファイルから注入することもできます。

```bash
uv run --env-file .env pytest examples/01_basic
```

テンプレートは [`examples/.env.example`](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli/blob/main/examples/.env.example) にあります。
ただし場所が `examples/` 配下なので、編集前にリポジトリルートへ `.env` としてコピーしてください。

```bash
cp examples/.env.example .env
```

コピーしたあとは、利用する環境に合わせて `.env` の値を書き換えてください。
