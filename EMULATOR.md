# Evaluating the ESP32 Emulator

[日本語](EMULATOR.ja.md)

[esp-emu](https://github.com/espressif/esp-emulator) is Espressif's emulator for ESP32-family chips. This page records whether it can stand in for hardware tests with this plugin, and gives a recipe for anyone who wants to use it anyway.

## Conclusion

- **This plugin does not support esp-emu, and there is no plan to.** Little of the hardware test suite can move to it, and hardware-free tests already have a host core.
- `pytest-embedded-espemu`, in the upstream pytest-embedded, assumes an ESP-IDF build and cannot be used from this plugin ([see below](#why-pytest-embedded-espemu-does-not-work)).
- You can still try it. A [recipe](#recipe-if-you-use-it-anyway) that replaces the upload with a `conftest.py` is given below. It relies on plugin internals and is unsupported.

Evaluated with esp-emu 0.50.0, arduino-cli 1.5.1, esp32:esp32 3.3.12 and lang-ship:host 1.7.1 on Linux x86_64 (WSL2), in October 2026.

## What runs in esp-emu

- It boots the `*.ino.merged.bin` that an Arduino-ESP32 build produces, as it stands.
- It exposes the UART over TCP, so this plugin's `socket://` path works unchanged. `dut`, `peers`, `expect`, Unity and ArduTest all work.
- WiFi (a built-in soft AP), TCP/UDP, NVS and the real FreeRTOS run. A panic produces a backtrace with source lines.
- Supported chips are **C3, C5, C6, H2, P4 and S3**. **The original ESP32 and the S2 are not supported.**

## Compared with a host core and hardware

The same sketches were run on a host core (`lang-ship:host:host`) and in esp-emu (C3).

| Item | host core | esp-emu | Hardware |
|---|---|---|---|
| ESP32-specific APIs (`ESP.*`, WebServer, ESPmDNS, `WiFi.onEvent`, ESP-NOW, BLE, `nvs_flash`, deep sleep, task WDT, Update) | none of the 10 builds | builds and boots | ○ |
| `malloc(1MB)` | succeeds | returns NULL | returns NULL |
| Creating a higher-priority task | the creator carries on first (priority is ignored) | the new task runs first | the new task runs first |
| Joining WiFi with a wrong password | `WL_CONNECTED` (a stub) | `WL_CONNECT_FAILED` | `WL_CONNECT_FAILED` |
| Writing through a null pointer | the process dies, and the last output never arrives | stops by default and writes a backtrace with source lines to the esp-emu log. With `--no-panic-intercept` it prints Guru Meditation and reboots | prints Guru Meditation and reboots |
| NVS | in memory only | survives a reset, lost across an upload | kept |
| Time | real time. The Clock Port can make it virtual | virtual. It keeps pace with real time while waiting, and falls behind under CPU load (1.5× slower on C3, 2.7× on S3) | real time |
| Ways to inject outside values | bus observation, plus hooks for analog values, interrupts, UART, SPI and I2C | a dummy I2C device that reads back what was written, UART1 over TCP, RMT loopback | the wired parts |
| Displays | LGFX rendering supported | none | ○ |
| Build time (core cache warm) | 7 s | 18 s | 18 s |
| Running one test module | about 3.6 s | about 1.1 s | depends on the upload |
| OS | Linux, macOS, Windows | Linux, macOS (no Windows build) | — |

The host and the target also disagree on the signedness of `char` and the size of `long`. This is left out of the evaluation, because code written with fixed-width types such as `uint8_t` and `uint32_t` is not affected.

## How much coverage would it add?

262 test sketches with hardware profiles were collected from external projects that use this plugin (see [Real Projects](TESTING_EXAMPLES.md) and others), and sorted by whether they could move to esp-emu. The sorting was done mechanically from includes and API names, so the borderline cases are rough.

| Category | Sketches | In esp-emu |
|---|---|---|
| USB, Classic BT, I2S, ADC, displays, SD | 133 | not supported |
| BLE peer tests | 72 | **esp-emu instances do not share a radio.** In EspBle's advertise_scan, both advertising and scanning start, but the peer is never found. Running them needs the peer side rewritten for Bumble, and the test then checks "ESP talks to Bumble" instead |
| IR/RMT, UART between boards, GPIO | 7 | partly, through loopback. Most of them assume wiring |
| Serial, logic, WiFi | 50 | **all 50 already have a host profile** |

Without rewriting tests, **almost nothing** that a host core cannot cover becomes coverable without hardware.

- **What only esp-emu can do:** run code that depends on ESP32-specific APIs without a board. That is all.
- **Failure-path tests (a WiFi authentication failure, a vanishing AP, corrupted NVS, heap exhaustion, a reset at a chosen moment):** easier to set up in esp-emu. They can also be built on hardware with a test sketch or a peer, though, so they add no coverage.
- **The gain is small:** a little extra coverage for people without a permanent bench, or on chips they do not own (C3, C6, H2 and so on). It does not justify building esp-emu support into the plugin and maintaining it.

## Why pytest-embedded-espemu does not work

pytest-embedded 2.9.3 has a `pytest-embedded-espemu` service. It assumes an ESP-IDF build, so it does not work with an Arduino build. These are the results of trying it:

| How it was invoked | Result |
|---|---|
| `--embedded-services espemu` with this plugin enabled | this plugin's `arduino-cli upload` fails first |
| `--embedded-services espemu` with the plugin disabled | `esp-emu does not support target None`. Detecting the chip needs `IdfApp` |
| `--embedded-services idf,espemu` with the plugin disabled | `flasher_args.json not found`. It needs ESP-IDF build output |

The service also connects the UART through stdio rather than TCP, and its supported chips do not include the S3 (C3, C6, H2, P4 and S31 as of 2.9.3).

## When to look again

Re-evaluate if any of these happens:

- esp-emu instances can talk to each other over BLE or ESP-NOW. BLE peer tests would then run without a bench.
- The original ESP32 is supported.
- There is a way to inject the behaviour of LCDs or external devices.
- A concrete need appears to check ESP32-specific APIs without hardware.

## Recipe if you use it anyway

> **Unsupported.** This `conftest.py` replaces a plugin internal, `ArduinoCliUploadConfig.upload`. An update to the plugin or to esp-emu can break it.

### Setup

1. Install esp-emu and put it on `PATH`. If it lives elsewhere, set the `ESP_EMU` environment variable to its path.
2. Add an esp-emu profile to `sketch.yaml`. **What marks it is a `port` of `socket://localhost` with no port number.**

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

3. Put the following `conftest.py` at the root of your tests, for example `tests/conftest.py`. pytest only reads a conftest from a directory inside the rootdir that is an ancestor of the test file.

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

With this recipe, examples 01, 04 and 05 and a two-board peer setup passed on both C3 and S3 (`CDCOnBoot=cdc`).

### How it works

1. The plugin never passes a `socket://` port to `arduino-cli upload`, so the upload port is `None`. When the conftest sees that, and the FQBN names a chip esp-emu supports, it boots esp-emu instead of uploading.
2. The UART and control ports are free ports, picked fresh on every upload.
3. Once esp-emu is up, the conftest writes `esp-emu.host-arduino.json` into the build directory. The plugin reads that file and fills in the port number of `socket://localhost`, exactly as it does for a host core.
4. esp-emu processes are tracked per build directory, so each peer gets a process of its own. A process is stopped before the same sketch is uploaded again, and all of them when the session ends.

Also keep in mind:

- With `--port=/dev/ttyACM0`, the conftest does nothing, so the same profile uploads to a board as usual.
- `socket://` ports are not device-locked.
- esp-emu's own log stays in `<build>/esp-emu.log`.

### Differences from hardware

- **Output right after boot is missed:** esp-emu starts printing about 0.1 s after launch and does not wait for a connection. Write the test to send a command and wait for the reply, as [examples/01_basic](examples/01_basic/) does.
- **Flash starts fresh on every upload:** NVS does not survive an upload. To check that it survives a reset, use `emu_control("reset")`.
- **`erase-flash` erases the firmware too:** after a reset the chip keeps printing `invalid header: 0xffffffff` and never boots. To clear only NVS, name the NVS partition, as in `emu_control("erase-region 0x9000 0x5000")`. Check the offset and size in `<build>/partitions.csv`.
- **`dut.serial.hard_reset()` does nothing:** `socket://` has no DTR/RTS. Use `emu_control("reset")` instead.
- **`CDCOnBoot=cdc` needs `--console usb-jtag`:** the conftest adds it for you.
- **WiFi joins the built-in AP:** the SSID is `myssid` and the password is `mypassword`.
  - `192.168.4.1`, as seen from the device, is the host's `127.0.0.1`.
  - To reach the device from the host, forward a port, as in `ESP_EMU_ARGS="--net user,hostfwd=tcp:127.0.0.1:18080-:80"`.
  - Without `--net`, Linux tries `tap0` first, so name `--net user` explicitly in CI.
- **Time is virtual:** allow longer timeouts than on hardware, and do not assert on real-time durations.
