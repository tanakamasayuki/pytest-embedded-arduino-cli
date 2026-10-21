# ESP32 エミュレーターの評価

[English](EMULATOR.md)

[esp-emu](https://github.com/espressif/esp-emulator) は、Espressif が公開している ESP32 系チップのエミュレーターです。このページには、esp-emu がこの plugin で実機テストの代わりになるかを評価した結果と、それでも使いたい場合のレシピをまとめます。

## 結論

- **この plugin は esp-emu に対応していません。今のところ対応する予定もありません。** 実機テストの代わりになる範囲がほとんどなく、実機のないテストには host core という手段がすでにあるためです。
- 上位の pytest-embedded にある `pytest-embedded-espemu` は、ESP-IDF のビルドを前提にしています。この plugin からは使えません([後述](#pytest-embedded-espemu-が使えない理由))。
- 試しに使うことはできます。`conftest.py` で upload を差し替える[レシピ](#それでも使う場合のレシピ)を載せておきます。plugin の内部に依存するので、サポート対象外です。

評価した環境: esp-emu 0.50.0、arduino-cli 1.5.1、esp32:esp32 3.3.12、lang-ship:host 1.7.1、Linux x86_64(WSL2)。2026 年 10 月に評価しました。

## esp-emu で動くもの

- Arduino-ESP32 のビルドで出力される `*.ino.merged.bin` を、そのまま起動できます。
- UART を TCP で公開するので、この plugin の `socket://` の経路は改造なしで動きます。`dut`、`peers`、`expect`、Unity、ArduTest も動きます。
- WiFi(内蔵の soft AP)、TCP/UDP、NVS、本物の FreeRTOS が動きます。panic したときは、ソースの行まで付いたバックトレースが出ます。
- 対応チップは **C3、C5、C6、H2、P4、S3** です。**ESP32 無印と S2 には対応していません。**

## host core と実機との比較

同じスケッチを、host core(`lang-ship:host:host`)と esp-emu(C3)で動かして比べました。

| 項目 | host core | esp-emu | 実機 |
|---|---|---|---|
| ESP32 固有の API(`ESP.*`、WebServer、ESPmDNS、`WiFi.onEvent`、ESP-NOW、BLE、`nvs_flash`、deep sleep、task WDT、Update) | 10 種すべてビルドできない | ビルドして起動できる | ○ |
| `malloc(1MB)` | 成功する | NULL が返る | NULL が返る |
| 優先度の高いタスクを作成したとき | 作成した側が先に進む(優先度は無視) | 新しいタスクが先に動く | 新しいタスクが先に動く |
| 誤ったパスワードで WiFi に接続 | `WL_CONNECTED`(スタブ) | `WL_CONNECT_FAILED` | `WL_CONNECT_FAILED` |
| null ポインタへの書き込み | プロセスが落ちる。直前の出力も届かない | 既定では停止し、ソース行付きのバックトレースを esp-emu のログに出す。`--no-panic-intercept` を付けると Guru Meditation を出して再起動する | Guru Meditation を出して再起動する |
| NVS | メモリ上だけ | リセットをまたいで残る。upload をまたぐと消える | 残る |
| 時間 | 実時間。Clock Port で仮想時間にもできる | 仮想時間。待機中は実時間と同じ速さで進み、CPU を使い続けると実時間より遅れる(C3 で 1.5 倍、S3 で 2.7 倍) | 実時間 |
| 外部の値を差し込む口 | バスの観測と、アナログ値・割り込み・UART・SPI・I2C のフック | I2C のダミー(書いた値を読み返すだけ)、UART1 の TCP、RMT の loopback | 配線した実物 |
| ディスプレイ | LGFX の描画に対応 | なし | ○ |
| ビルド時間(core のキャッシュあり) | 7 秒 | 18 秒 | 18 秒 |
| テスト 1 モジュールの実行時間 | 約 3.6 秒 | 約 1.1 秒 | upload の時間による |
| 動く OS | Linux、macOS、Windows | Linux、macOS(Windows 版の配布はない) | — |

`char` の符号や `long` のサイズも host とターゲットでは違います。ただ、`uint8_t` や `uint32_t` のように幅の決まった型で書いていれば問題にならないので、評価の材料には入れていません。

## カバー範囲はどれだけ広がるか

この plugin を使っている外部のプロジェクト([実プロジェクト集](TESTING_EXAMPLES.ja.md) など)から、実機用の profile を持つテスト用スケッチを 262 本集め、esp-emu に移せるかを分類しました。分類は include と API 名で機械的に行ったので、境界の判定は粗いです。

| 分類 | 本数 | esp-emu での扱い |
|---|---|---|
| USB、Classic BT、I2S・ADC・ディスプレイ・SD | 133 | 対応していない |
| BLE の peer テスト | 72 | **esp-emu 同士は無線でつながらない。** EspBle の advertise_scan で、advertise とスキャンはどちらも始まるのに、相手は見つからないことを確かめた。動かすには peer 側を Bumble で書き直す必要があり、そうするとテストの意味が「ESP と Bumble で通信できること」に変わる |
| IR/RMT、ボード間の UART、GPIO | 7 | loopback で一部だけ動く。配線が前提のものが多い |
| serial・ロジック・WiFi | 50 | **50 本すべてに、すでに host profile がある** |

host core ではできず、実機なしでカバーできるようになる範囲は、テストを書き直さない限り**ほぼゼロ**でした。

- **esp-emu でしかできないこと:** ESP32 固有の API に依存するコードを、実機なしで動かすことだけです。
- **異常系のテスト(WiFi の認証失敗、AP の消失、NVS の破損、ヒープ不足、任意のタイミングでのリセット):** esp-emu のほうが手軽に作れます。ただ、実機でもテスト用のスケッチや peer を工夫すれば作れるので、カバー範囲は増えません。
- **広がる範囲は限られる:** 常駐のベンチがない人や、手元にないチップ(C3、C6、H2 など)で、カバー範囲が少し広がる程度です。plugin に組み込んで保守する労力には見合いません。

## pytest-embedded-espemu が使えない理由

pytest-embedded 2.9.3 には `pytest-embedded-espemu` サービスがあります。ただし、ESP-IDF のビルドを前提にしているので、Arduino のビルドでは使えません。実際に試した結果です。

| 指定方法 | 結果 |
|---|---|
| この plugin を有効にしたまま `--embedded-services espemu` | この plugin の `arduino-cli upload` が先に失敗する |
| plugin を無効にして `--embedded-services espemu` | `esp-emu does not support target None`。チップの判定に `IdfApp` が必要 |
| plugin を無効にして `--embedded-services idf,espemu` | `flasher_args.json not found`。ESP-IDF のビルド結果が必要 |

このサービスは、UART を TCP ではなく標準入出力でつなぎます。また、対応チップに S3 が入っていません(2.9.3 時点で C3、C6、H2、P4、S31)。

## 見直す条件

次のどれかが実現したら、評価をやり直します。

- esp-emu 同士を BLE や ESP-NOW でつなげるようになる。BLE の peer テストが、ベンチなしで動くようになります。
- ESP32 無印に対応する。
- LCD や外部機器の振る舞いを差し込む口ができる。
- 実機なしで ESP32 固有の API を検証したい、という具体的な需要が出てくる。

## それでも使う場合のレシピ

> **サポート対象外です。** この `conftest.py` は、plugin の内部(`ArduinoCliUploadConfig.upload`)を差し替えています。plugin や esp-emu の更新で動かなくなることがあります。

### 準備

1. esp-emu をインストールし、`PATH` に通します。別の場所に置く場合は、環境変数 `ESP_EMU` にパスを設定します。
2. `sketch.yaml` に、esp-emu 用の profile を追加します。**`port` を、ポート番号なしの `socket://localhost` にするのが目印です。**

```yaml
profiles:
  esp32c3-emu:
    fqbn: esp32:esp32:esp32c3
    port: socket://localhost
    platforms: &esp32
      - platform: esp32:esp32 (3.3.12)
        platform_index_url: https://espressif.github.io/arduino-esp32/package_esp32_index.json
  esp32s3-emu:
    fqbn: esp32:esp32:esp32s3:CDCOnBoot=cdc
    port: socket://localhost
    platforms: *esp32
```

3. 次の `conftest.py` を、テストのルート(例: `tests/conftest.py`)に置きます。pytest が conftest を読むのは、rootdir の中にあって、テストファイルの祖先にあたるディレクトリだけです。

```python
"""Run ESP32 sketches in esp-emu instead of uploading them to a board.

A profile is emulated when its port is `socket://localhost` (no port number)
and its FQBN names a chip esp-emu supports. Everything else uploads as usual.
Unsupported: this replaces a plugin internal.
"""
import json
import os
import shlex
import socket
import subprocess
import time
from pathlib import Path

import pytest
from pytest_embedded_arduino_cli import flasher

EMU_CHIPS = {"esp32c3", "esp32c5", "esp32c6", "esp32h2", "esp32p4", "esp32s3"}
BOOT_TIMEOUT = 10.0

_original_upload = flasher.ArduinoCliUploadConfig.upload
_procs: dict[Path, tuple[subprocess.Popen, int]] = {}  # build path -> (process, control port)


def _fqbn(build_path: Path) -> str | None:
    try:
        return json.loads((build_path / "build.options.json").read_text())["fqbn"]
    except (OSError, ValueError, KeyError):
        return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stop(build_path: Path) -> None:
    entry = _procs.pop(build_path, None)
    if entry and entry[0].poll() is None:
        entry[0].terminate()
        entry[0].wait(5)
    (build_path / "esp-emu.host-arduino.json").unlink(missing_ok=True)


def _emu_upload(self, *, check=True):
    build = Path(self.build_path)
    fqbn = _fqbn(build)
    parts = (fqbn or "").split(":", 3)
    # A real port means a board is attached: upload to it as usual.
    if self.port or parts[:2] != ["esp32", "esp32"] or parts[2] not in EMU_CHIPS:
        return _original_upload(self, check=check)

    _stop(build)
    opts = parts[3] if len(parts) > 3 else ""
    uart_port, control_port = _free_port(), _free_port()
    cmd = [
        os.environ.get("ESP_EMU", "esp-emu"),
        "--chip", parts[2],
        "--firmware", str(next(build.glob("*.ino.merged.bin"))),
        "--elf", str(next(build.glob("*.ino.elf"))),
        # Arduino's HWCDC does not set the ROM console selector, so name it.
        "--console", "usb-jtag" if "CDCOnBoot=cdc" in opts else "auto",
        "--uart-tcp", f"127.0.0.1:{uart_port}",
        "--control-tcp", f"127.0.0.1:{control_port}",
        *shlex.split(os.environ.get("ESP_EMU_ARGS", "")),
    ]
    print(f"[esp-emu] {shlex.join(cmd)}")
    log = open(build / "esp-emu.log", "w")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                            env={**os.environ, "RUST_LOG": os.environ.get("RUST_LOG", "warn")})
    _procs[build] = (proc, control_port)

    deadline = time.monotonic() + BOOT_TIMEOUT
    while True:
        if proc.poll() is not None:
            raise RuntimeError(f"esp-emu exited with {proc.returncode}; see {build / 'esp-emu.log'}")
        try:
            socket.create_connection(("127.0.0.1", control_port), 0.2).close()
            break
        except OSError:
            if time.monotonic() > deadline:
                raise TimeoutError(f"esp-emu did not open its ports; see {build / 'esp-emu.log'}")
            time.sleep(0.05)

    # The plugin completes socket://localhost from this file, as for a host core.
    (build / "esp-emu.host-arduino.json").write_text(json.dumps({"pid": proc.pid, "port": uart_port}))
    return subprocess.CompletedProcess(cmd, 0)


def pytest_configure(config):
    flasher.ArduinoCliUploadConfig.upload = _emu_upload


def pytest_unconfigure(config):
    for build in list(_procs):
        _stop(build)


@pytest.fixture
def emu_control(arduino_cli_app):
    """Send one command to the primary DUT's control channel, e.g. "reset"."""
    entry = _procs.get(Path(arduino_cli_app.build_path))
    if entry is None:
        pytest.skip("not running in esp-emu")

    def send(command: str) -> str:
        with socket.create_connection(("127.0.0.1", entry[1]), 5) as s:
            s.sendall(command.encode() + b"\n")
            return s.makefile().readline().strip()

    return send
```

```bash
uv run pytest tests --profile esp32c3-emu
```

このレシピで、examples の 01、04、05 と、peer を 2 台使う構成が、C3 と S3(`CDCOnBoot=cdc`)の両方で PASS することを確かめました。

### 仕組み

1. plugin は、`socket://` の port を `arduino-cli upload` に渡しません。そのため upload の port は `None` になります。conftest はこれを見て、FQBN が esp-emu の対応チップであれば、upload の代わりに esp-emu を起動します。
2. UART 用と control 用のポートは、upload のたびに空いているものを割り当てます。
3. 起動したら、build ディレクトリに `esp-emu.host-arduino.json` を書きます。plugin は host core のときと同じく、このファイルを見て `socket://localhost` にポート番号を補います。
4. esp-emu のプロセスは build ディレクトリごとに管理します。そのため peer の分も別のプロセスとして起動します。同じスケッチを次に upload する前と、セッションが終わるときに止めます。

このほか、次の点も覚えておいてください。

- `--port=/dev/ttyACM0` を指定すると、conftest は何もしません。同じ profile のまま、実機で通常どおり upload します。
- `socket://` の port には device lock がかかりません。
- esp-emu 自身のログは `<build>/esp-emu.log` に残ります。

### 実機と違う点

- **起動直後の出力を取りこぼす:** esp-emu は起動から約 0.1 秒で出力を始め、接続を待ちません。[examples/01_basic](examples/01_basic/) のように、コマンドを送って応答を待つ形で書いてください。
- **upload のたびに flash が初期化される:** upload をまたいで NVS は残りません。リセットをまたいで残ることは、`emu_control("reset")` で確かめます。
- **`erase-flash` は firmware も消す:** 消した後にリセットすると、`invalid header: 0xffffffff` を出し続けて起動しません。NVS だけを消すときは、`emu_control("erase-region 0x9000 0x5000")` のように NVS パーティションを指定します。オフセットとサイズは `<build>/partitions.csv` で確かめてください。
- **`dut.serial.hard_reset()` は効かない:** `socket://` には DTR/RTS がないためです。代わりに `emu_control("reset")` を使います。
- **`CDCOnBoot=cdc` には `--console usb-jtag` が必要:** conftest が自動で付けます。
- **WiFi は内蔵の AP につながる:** SSID は `myssid`、パスワードは `mypassword` です。
  - デバイスから見た `192.168.4.1` は、ホストの `127.0.0.1` です。
  - ホストからデバイスにつなぐには、`ESP_EMU_ARGS="--net user,hostfwd=tcp:127.0.0.1:18080-:80"` のように転送の設定が必要です。
  - `--net` を指定しないと、Linux ではまず `tap0` を試します。CI では `--net user` を明示してください。
- **時間は仮想時間:** timeout は実機より長めに取り、実時間での長さを assert しないでください。
