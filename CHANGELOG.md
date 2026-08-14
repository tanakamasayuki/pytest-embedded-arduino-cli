# Changelog / 変更履歴

## Unreleased
- (EN) Resolve device lock keys through symlinks, so `/dev/serial/by-id/...` and `/dev/serial/by-path/...` aliases lock the same physical device as the underlying `/dev/ttyUSB*` node. Non-path keys (`COM3`, `--device-lock-key` labels) are unchanged.
- (JA) device lock key の symlink を解決するように変更。`/dev/serial/by-id/...` や `/dev/serial/by-path/...` を指定しても実体の `/dev/ttyUSB*` と同じ device として排他制御される。path でない key（`COM3` や `--device-lock-key` の label）は従来どおり。

## 1.4.0
- (EN) Write result files into the `pytest-embedded` log directory: one `PASSED.txt`/`FAILED.txt`/`ERROR.txt`/`SKIPPED.txt`/`XFAILED.txt`/`XPASSED.txt` per test directory, a zero-byte root marker whose name carries the counts (e.g. `FAILED-2_PASSED-7`), plus `SUMMARY.txt` and `summary.json`. Disable with `--arduino-cli-no-log-summary`.
- (JA) `pytest-embedded` の log directory に結果ファイルを出力。各テスト directory に `PASSED.txt`/`FAILED.txt`/`ERROR.txt`/`SKIPPED.txt`/`XFAILED.txt`/`XPASSED.txt` のいずれか 1 つ、root には件数を名前に持つ 0 byte の marker（例: `FAILED-2_PASSED-7`）、加えて `SUMMARY.txt` と `summary.json` を出力。`--arduino-cli-no-log-summary` で無効化可能。

## 1.3.3
- (EN) Compile detected peer DUT sketches before primary upload so all compile work completes before any upload begins; peer upload/connect still only runs when the `peers` fixture is requested.
- (JA) 検出された peer DUT sketch を primary upload 前に compile し、すべての compile が終わってから upload に進むように変更。peer の upload / connect は引き続き `peers` fixture が要求された場合のみ実行。

## 1.3.2
- (EN) Keep the primary DUT device lock in the module-level lock manager so it remains held during test execution and is released at module teardown.
- (JA) primary DUT の device lock を module-level lock manager で保持し、テスト実行中も解放せず module teardown で解放するように修正。

## 1.3.1
- (EN) Fix peer DUT device locks so they are held until module teardown instead of being released at the end of the `peers` fixture call.
- (JA) peer DUT の device lock が `peers` fixture 呼び出し終了時に解放されず、module teardown まで保持されるように修正。
- (EN) Document the default device lock directory resolution order and how to override it with `--device-lock-dir`.
- (JA) device lock directory の既定解決順と、`--device-lock-dir` による上書き方法をドキュメントに追記。

## 1.3.0
- (EN) Add device locking for physical serial DUTs. The default `--device-lock=auto` lets builds run first, then waits before upload and holds each lock until that DUT use finishes; peer DUTs are locked by their resolved serial ports when the `peers` fixture is requested, and `socket://...` targets are left unlocked by default.
- (JA) 物理 serial DUT 向けの device lock を追加。既定値の `--device-lock=auto` では build を先に実行し、upload 直前で待機して各 DUT の利用終了まで lock を保持する。peer DUT は `peers` fixture が要求された時点で解決済み serial port により lock し、`socket://...` target は既定では lock しない。
- (EN) Add `--device-lock-timeout`, `--device-lock-dir`, and `--device-lock-key` options, and use OS file locking via `portalocker` so leftover lock files after forced termination do not keep devices locked by themselves.
- (JA) `--device-lock-timeout`、`--device-lock-dir`、`--device-lock-key` option を追加。`portalocker` による OS file lock を使うため、強制終了後に lock file が残っても、それだけで device が lock され続けることはない。

## 1.2.2
- (EN) Fall back to empty C/C++ compile properties (`compiler.cpp.extra_flags` and `compiler.c.extra_flags`) when auto-selecting the `build_config.toml` injection target, so ESP32 boards that populate both `build.extra_flags` and `build.defines` (for example PSRAM-enabled boards) no longer fail detection.
- (JA) `build_config.toml` の注入先自動選択で、`build.extra_flags` と `build.defines` の両方が埋まっている ESP32 board（PSRAM 有効 board など）向けに、空の C/C++ compile property（`compiler.cpp.extra_flags` / `compiler.c.extra_flags`）へ fallback するように変更。

## 1.2.1
- (EN) Drain any remaining received serial bytes when the connection closes, so `dut.log` is not cut mid-line and reaches roughly `-s` console completeness (best-effort, not a full guarantee). Document how to capture the full trailing output deterministically (device end marker or a `pexpect.TIMEOUT` drain).
- (JA) シリアル接続を閉じる際に受信済みの残りバイトをドレインし、`dut.log` が行の途中で切れず `-s` コンソール相当まで埋まるように改善（ベストエフォートで完全保証ではない）。末尾出力を確実に残す方法（終端マーカー / `pexpect.TIMEOUT` ドレイン）も README に追記。

## 1.2.0
- (EN) Auto-select the `--build-property` target for `build_config.toml` defines/flags by probing `arduino-cli compile --show-properties`: use `build.extra_flags` when empty (host / AVR) and `build.defines` on ESP32, instead of overwriting ESP32's platform-populated `build.extra_flags`. Fail with a clear error when no candidate is empty.
- (JA) `build_config.toml` の defines/flags を渡す `--build-property` の対象を `arduino-cli compile --show-properties` の検査で自動選択。空なら `build.extra_flags`（host / AVR）、ESP32 では platform が値を入れた `build.extra_flags` を上書きせず `build.defines` を使用。どの候補も空でない場合は明確なエラーで停止。
- (EN) Add a `build_property` override in `build_config.toml` (top-level and per-profile `[profiles.<name>].build_property`) to pin the injection target and skip the detection probe.
- (JA) 注入先を固定して検出プローブを省ける `build_property` override を `build_config.toml` に追加（トップレベルおよび profile 別 `[profiles.<name>].build_property`）。

## 1.1.7
- (EN) Add `arduino_test.reset()`, which sends the protocol `RESET_STATE` command, discards the cached test list, and re-synchronizes with `HELLO` on the next run.
- (JA) protocol の `RESET_STATE` を送信し、キャッシュした test 一覧を破棄して次回実行時に `HELLO` で再同期する `arduino_test.reset()` を追加。
- (EN) Add `ArduTestResult.duration`, a host-measured wall-clock time from `RUN` to `RESULT` (approximate; includes serial round-trip latency; `None` for skipped tests).
- (JA) `RUN` から `RESULT` までを host 側の壁時計時間で計測する `ArduTestResult.duration` を追加（概算で serial 往復遅延を含む。skip 時は `None`）。
- (EN) Add `ArduTestResult.artifact_files` and `arduino_test.artifact_files`, a unified accessor that lists both text and binary artifacts with filename, content type, `binary` flag, and saved path.
- (JA) text / binary 両方の artifact を、ファイル名・content type・`binary` flag・保存パス付きで列挙する統合アクセサ `ArduTestResult.artifact_files` / `arduino_test.artifact_files` を追加。
- (EN) Verify the device protocol version during `HELLO` and abort with an error on mismatch; record `device_protocol_version`, `device_library`, and `device_library_version` on the session.
- (JA) `HELLO` 時に device の protocol version を検証し、不一致ならエラーで中止。session に `device_protocol_version` / `device_library` / `device_library_version` を記録するように変更。

## 1.1.6
- (EN) Sort per-profile `tests` entries in `state.json` by pytest nodeid when saving.
- (JA) `state.json` 保存時に profile ごとの `tests` entry を pytest nodeid 順に並べるように変更。

## 1.1.5
- (EN) Add `--save-state` and `--save-state-dir` options to save test verification state to `state.json` for local development. State is recorded per profile with per-test timestamps. For peer tests, only the primary DUT state is recorded. Feature is disabled by default.
- (JA) ローカル開発用にテストの検証状態を `state.json` に記録する `--save-state` と `--save-state-dir` option を追加。Profile ごと、test ごとのタイムスタンプを記録。peer test では primary DUT のみ記録。既定値は無効。

## 1.1.4
- (EN) Fix peer DUT sending failure
- (JA) peer DUT に送信できなかったのを修正

## 1.1.3
- (EN) Add peer DUT support through `peer_<name>` sketch directories, the `peers` fixture, and per-peer `--peer-profile` / `--peer-port` options.
- (JA) `peer_<name>` sketch directory、`peers` fixture、peer ごとの `--peer-profile` / `--peer-port` option による peer DUT 対応を追加。
- (EN) Add `examples/12_peer_host_core` as a minimal host Arduino core peer DUT example without DUT-to-DUT communication.
- (JA) DUT 間通信を行わない最小の host Arduino core peer DUT 例として `examples/12_peer_host_core` を追加。
- (EN) Avoid completing peer `socket://` runtime ports in `--run-mode=build`, because upload has not generated host Arduino port metadata yet.
- (JA) `--run-mode=build` では upload 前で host Arduino の port 情報が未生成のため、peer の `socket://` runtime port 補完を行わないように修正。

## 1.1.2
- (EN) Add `arduino_test.set_config()` and `arduino_test.set_capability()` for fixed test-local ArduTest config and capability values without environment patching.
- (JA) 環境変数の patch なしで test-local な ArduTest config / capability 固定値を渡せる `arduino_test.set_config()` と `arduino_test.set_capability()` を追加。
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
