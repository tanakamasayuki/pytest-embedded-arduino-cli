# 08_arduino_ide_project

この例は、Arduino IDE でそのまま開ける sketch プロジェクトに近い構成を示します。

- テスト対象コードは通常の Arduino sketch ディレクトリに置きます
- テスト用ワークスペースは `tests/` 配下に置きます
- `uv` は `tests/` をルートとして実行します
- build、upload、profile 選択、port 解決はこの plugin が担当します
- この example は、ほかの `examples/0x_*` と同じ実行前提ではなく、独立したプロジェクト例として扱います
- `pyproject.toml` や `.env.example` は `demo_add_sketch/tests/` 側にあり、`uv` の `.venv` もそのワークスペースで別に管理されます

この構成では Arduino IDE 互換を優先するため、`07_arduino_library_project` のようにテスト対象コードをライブラリとしてきれいに分離できません。
そのため、test runner 側では薄いラッパーファイルを明示的に置いて、実際の sketch 側の `.h` / `.cpp` を `#include` します。

実際のサンプルプロジェクトは `demo_add_sketch/` 配下にあります。
