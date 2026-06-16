# 12_peer_host_core

[English](README.md)

host Arduino core で `peers` fixture を使う最小サンプルです。

このサンプルでは、primary DUT と peer DUT の間で通信は行いません。
目的は、次の最小構成を示すことです。

- primary sketch は `dut` として扱われる
- `peer_echo/` が peer DUT として検出される
- `peers` fixture を要求すると peer DUT も build / upload / connect される
- peer DUT は `peers["echo"]` で参照できる
- 両方の DUT が Python からの `ready?` handshake に応答する

想定コマンド:

```bash
uv run pytest examples/12_peer_host_core --profile host
```

primary DUT は `--profile host` を使います。
peer DUT は `--profile` を継承しませんが、`peer_echo/sketch.yaml` に `default_profile: host` があるため、`--peer-profile` なしで動きます。

peer profile を明示する場合:

```bash
uv run pytest examples/12_peer_host_core --profile host --peer-profile echo:host
```

どちらの sketch も `port: socket://localhost` を使うため、plugin は DUT ごとの `*.host-arduino.json` を読み取り、runtime socket URL を補完します。

## 起動順

plugin は primary DUT を先に upload します。
テストが `peers` fixture を要求した場合、その後に peer DUT を peer 名順で upload / connect し、最後に通常の `dut` fixture が primary DUT へ接続します。

このサンプルでは、起動直後に一度だけ READY を出す方式は使いません。
pytest が接続した後に各 DUT へ `ready?` を送り、それぞれの READY 応答を確認します。
サンプルを軽く保ちつつ、実機 serial でも取りこぼしにくい形にしています。
