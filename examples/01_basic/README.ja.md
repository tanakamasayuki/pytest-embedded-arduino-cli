# 01_basic

[English](README.md)

最初に試すための最小サンプルです。[最初のテスト](../../FIRST_TEST.ja.md)で作るtestの、リポジトリ内で実行できる対応例です。

- デフォルト profile は `esp32` です
- `uno` のような他の target を使いたい場合は `--profile` を明示して切り替えます
- 実際の sketch は `basic/` 配下に置いています

このサンプルは `default_profile: esp32` を定義しているため、`--profile` なしでも動きます。

boardによっては、serial portへ接続できても起動直後のテキストをまだ受け取れません。また、sketchが起動直後に一度だけ出力したテキストをpytest側が取りこぼす場合もあります。そのような1回だけの送受信をテストの前提にすると、sketchが正常でも失敗する可能性があります。

そこで、このテストはpytestから `ping` を繰り返し送り、sketchの `PONG` 応答を確認するreadiness handshakeを使います。実際に双方向通信できた時点で成功とするため、起動直後の特定の1回が届くことには依存しません。成功時は `1 passed` と表示されます。詳しいtimeout設計は[最初のテスト](../../FIRST_TEST.ja.md#起動直後のserial通信をそのままテストしない)で説明しています。

実行例:

```bash
uv run pytest examples/01_basic --profile=esp32 --port=/dev/ttyUSB0
```

sketch を直接指定しても構いません。

```bash
uv run pytest examples/01_basic/basic --profile=esp32 --port=/dev/ttyUSB0
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
