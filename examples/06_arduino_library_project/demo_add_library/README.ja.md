# demo_add_library

これは、実プロジェクト向けのテスト構成例として用意した小さな Arduino ライブラリです。

プロジェクトルート:

- `library.properties`
- `src/`
- `tests/`

テストルート:

- `tests/pyproject.toml`
- `tests/pytest.ini`
- `tests/.env.example`
- `tests/run.sh`、`tests/run.bat` などの補助スクリプト

実行コマンドは `tests/` から使います。

例:

```bash
cd examples/06_arduino_library_project/demo_add_library/tests
cp .env.example .env
uv run --env-file .env pytest serial_runner --profile esp32
```

`serial_runner` はライブラリを直接使う最小例です。
`unity_runner` は同じプロジェクト構成の中で、ESP32 の Unity を使う例です。

各 runner は `.ino` と同じ場所にそれぞれの `sketch.yaml` を持ちます。
この例では `sketch.yaml` の `libraries: - dir: ../../` でライブラリルートを参照しています。
