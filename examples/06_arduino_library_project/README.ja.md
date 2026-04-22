# 06_arduino_library_project

この例は、Arduino ライブラリの実プロジェクトに近い構成を示します。

- ライブラリ本体はプロジェクトルートに置きます
- テスト用ワークスペースは `tests/` 配下に置きます
- `uv` は `tests/` をルートとして実行します
- build、upload、profile 選択、port 解決はこの plugin が担当します

構成は実際の Arduino ライブラリプロジェクトに近い形に寄せています。

実際のサンプルプロジェクトは `demo_add_library/` 配下にあります。
