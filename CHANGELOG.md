# Changelog / 変更履歴

## Unreleased
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
