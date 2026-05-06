# Changelog / 変更履歴

## Unreleased
- (EN) Add `--arduino-test-missing-config=skip|error` to choose whether missing required ArduTest config skips tests or raises an error.
- (JA) ArduTest の必須 config が未指定だった場合に test を skip するか error にするかを選べる `--arduino-test-missing-config=skip|error` を追加。
- (EN) Add `--arduino-test-artifact-dir` for ArduTest artifact output, defaulting to `ardutest` under pytest `rootdir`, with lazy directory creation and `--clean` removal.
- (JA) ArduTest artifact の保存先を指定する `--arduino-test-artifact-dir` を追加。既定値は pytest `rootdir` 配下の `ardutest` とし、保存時のみ directory を作成し、`--clean` 時に削除するように変更。
- (EN) Save ArduTest `ARTIFACT_BINARY` payloads as raw bytes without Base64 decoding, alongside existing text artifact saving.
- (JA) ArduTest の `ARTIFACT_BINARY` payload を Base64 ではなく raw bytes のまま保存するようにし、既存の text artifact 保存と併せて扱うように変更。

## 1.1.1
- (EN) Add pytest `--clean` option and pass it through to `arduino-cli compile --clean`.
- (JA) pytest の `--clean` option を追加し、`arduino-cli compile --clean` として渡すように変更。
- (EN) Add experimental `arduino_test` fixture support for sketches that declare the separate ArduTest Arduino library in `sketch.yaml`, including test listing, requirement/config handling, logs, metrics, text artifacts, and assertion failure collection.
- (JA) `sketch.yaml` で別管理の ArduTest Arduino ライブラリを宣言する sketch 向けに、実験的な `arduino_test` fixture を追加し、test 一覧取得、requirement/config 処理、log、metric、text artifact、assertion failure の収集に対応。
- (EN) Add `examples/11_ardutest` with split basic and metadata/config examples for the experimental `arduino_test` fixture.
- (JA) experimental な `arduino_test` fixture 向けに、basic と metadata/config を分けた `examples/11_ardutest` を追加。
- (EN) Update ArduTest protocol handling to use length-prefixed payloads for logs, text artifacts, failures, and protocol errors.
- (JA) ArduTest protocol の log、text artifact、failure、protocol error を length-prefixed payload 形式で扱うように更新。
- (EN) Batch `socket://` serial reads for host Arduino core runs to avoid very slow one-byte-at-a-time redirect behavior.
- (JA) host Arduino core の `socket://` 実行で 1 byte ずつ redirect されて遅くなる問題を避けるため、serial read を chunk 化。
- (EN) Reset internally completed host socket ports for each sketch so multi-sketch runs do not reuse the previous runtime port.
- (JA) 複数 sketch の実行で前の runtime port を再利用しないよう、内部補完した host socket port を sketch ごとにリセットするように修正。
- (EN) Auto-resolve host socket ports from `profiles.<profile>.port` in `sketch.yaml` when no CLI or environment port is specified.
- (JA) CLI または環境変数で port が未指定の場合に、`sketch.yaml` の `profiles.<profile>.port` から host socket port を自動解決するように変更。
- (EN) Add `examples/09_host_arduino_core` for host-machine Arduino core smoke tests with socket port auto-completion.
- (JA) host machine 上で Arduino core を実行する smoke test 例として、socket port の自動補完を含む `examples/09_host_arduino_core` を追加。
- (EN) Add `[flags]` support in `build_config.toml` for value-less compile-time defines and add `examples/10_build_flags`.
- (JA) `build_config.toml` の `[flags]` で値なし compile-time define を渡せるようにし、`examples/10_build_flags` を追加。

## 1.1.0
- (EN) Skip unsupported `--profile` values before build by treating profiles listed in `sketch.yaml` as the supported set for each sketch.
- (JA) `sketch.yaml` に定義された profile を各 sketch の対応 profile とみなし、未対応の `--profile` は build 前に skip するように変更。
- (EN) Expanded and reorganized `examples/` and related documentation, including basic usage samples, persistence / erase behavior, Unity-based testing, and independent project examples for both Arduino library-style and Arduino IDE-style layouts.
- (JA) `examples/` と関連ドキュメントを拡充・整理し、基本的な使い方のサンプル、永続領域と erase 挙動、Unity ベースのテストに加えて、Arduino ライブラリ形式と Arduino IDE 向け sketch 形式の独立した実プロジェクト例を追加・再構成。

## 1.0.0
- (EN) Changed README language links to absolute GitHub URLs to avoid 404 on PyPI.
- (JA) PyPI 上で 404 にならないよう、README の言語切り替えリンクを GitHub 絶対 URL に変更。

## 0.2.0
- (EN) Initial release.
- (JA) 初期リリース。
