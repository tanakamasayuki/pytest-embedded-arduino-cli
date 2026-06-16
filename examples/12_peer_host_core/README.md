# 12_peer_host_core

[日本語版 (Japanese)](README.ja.md)

This sample demonstrates the `peers` fixture with a host Arduino core.

It intentionally does not make the primary DUT and peer DUT communicate with each other.
The goal is only to show the minimum layout where:

- the primary sketch is exposed as `dut`
- `peer_echo/` is detected as a peer DUT
- requesting the `peers` fixture builds, uploads, and connects the peer DUT
- the peer DUT can be accessed as `peers["echo"]`
- both DUTs answer a small Python-initiated `ready?` handshake

Expected command:

```bash
uv run pytest examples/12_peer_host_core --profile host
```

The primary DUT uses `--profile host`.
The peer DUT does not inherit `--profile`; it runs without `--peer-profile` because `peer_echo/sketch.yaml` defines `default_profile: host`.

To select the peer profile explicitly:

```bash
uv run pytest examples/12_peer_host_core --profile host --peer-profile echo:host
```

Both sketches use `port: socket://localhost`, so the plugin reads each generated `*.host-arduino.json` file and completes the runtime socket URL for each DUT.

## Startup Order

The plugin uploads the primary DUT first.
When the test requests `peers`, it then uploads and connects peer DUTs in peer name order, and finally the normal `dut` fixture connects to the primary DUT.

This sample avoids one-shot boot messages.
The test sends `ready?` to each DUT after pytest has connected, then expects each READY response.
That keeps the sample small while matching a safer pattern for real serial hardware.
