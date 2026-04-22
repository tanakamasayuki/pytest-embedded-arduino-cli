# 07_arduino_library_project

この例は、Arduino ライブラリの実プロジェクトに近い構成を示します。

- ライブラリ本体はプロジェクトルートに置きます
- テスト用ワークスペースは `tests/` 配下に置きます
- `uv` は `tests/` をルートとして実行します
- build、upload、profile 選択、port 解決はこの plugin が担当します
- この example は、ほかの `examples/0x_*` と同じ実行前提ではなく、独立したプロジェクト例として扱います
- `pyproject.toml` や `.env.example` は `demo_add_library/tests/` 側にあり、`uv` の `.venv` もそのワークスペースで別に管理されます

構成は実際の Arduino ライブラリプロジェクトに近い形に寄せています。

実際のサンプルプロジェクトは `demo_add_library/` 配下にあります。
