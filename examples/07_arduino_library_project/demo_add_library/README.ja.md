# demo_add_library

これは、実プロジェクト向けのテスト構成例として用意した小さな Arduino ライブラリです。

プロジェクトルート:

- `library.properties`
- `src/`
- `tests/`
- `.gitignore`

テストルート:

- `tests/pyproject.toml`
- `tests/pytest.ini`
- `tests/.env.example`
- `tests/run_wsl.sh`

`tests/pyproject.toml` は、このテストワークスペースを `uv` で実行するための設定です。
この例では必須依存に `pytest-html` も追加しています。
なくてもテスト自体は動きますが、結果を `report.html` として確認できるので、実プロジェクトではあると便利です。

`tests/pytest.ini` には、その HTML レポート出力設定を入れています。
あわせて、`pytest-embedded` 由来の実用上ほぼ意味のない warning を無視する設定も入れています。

プロジェクトルートの `.gitignore` は、このリポジトリのトップと同じ方針に寄せています。
Python / `uv` のローカル生成物、HTML レポート、各種キャッシュを無視しつつ、この構成向けに runner ごとの `tests/**/build/` も追加しています。

実行コマンドは `tests/` から使います。

例:

```bash
cd examples/07_arduino_library_project/demo_add_library/tests
cp .env.example .env
uv run --env-file .env pytest basic_runner --profile esp32
```

`basic_runner` はライブラリを直接使う最小例です。

各 runner は `.ino` と同じ場所にそれぞれの `sketch.yaml` を持ちます。
この例では `sketch.yaml` の `libraries: - dir: ../../` でライブラリルートを参照しています。

## run_wsl.sh

`run_wsl.sh` は、WSL 上で build だけを実行し、upload と test は Windows 側で実行するためのスクリプト例です。

- Windows 環境では build が遅いことがあり、WSL 側で実行した方が高速な場合があります
- 一方で serial port の扱いは Windows 側の方が単純なことが多いため、この例では転送とテストは Windows 側へ分けています

WSL 側でも USB/IP などを使えば Windows 上の serial port を利用できます。
その方法を使っても構いませんが、USB/IP を使えない環境や、使いたくない環境ではこのように build と upload を分けて運用できます。

また、WSL 上で build するときは、Windows 管理下のパスよりも WSL 管理下のパスの方が高速なことがあります。
そのためこの例では、ソースは WSL 側のワークスペースで扱う前提にしています。

また、WSL 側の `.venv` と Windows 側の `.venv` は同じパスで共存できません。
両方から `uv` を使う場合は、別々の配置先を使う必要があります。

この例では、WSL 側は `tests/.venv` をそのまま使い、Windows 側は `.env` の `UV_PROJECT_ENVIRONMENT_WIN` を使って `%TEMP%/.venv.pytest` に別の環境を作る想定です。
そのため、Windows 側で利用する `.venv` の配置先を `.env` から切り替えられるようにしています。
