# 09_host_arduino_core

This sample is intended for a board core that builds and runs Arduino sketches on the host machine.

Target board core:

- package index: `https://tanakamasayuki.github.io/host-arduino-core/package_index.json`
- FQBN: `lang-ship:host:host`

`arduino-cli compile` builds a host executable with local tools such as gcc.
`arduino-cli upload` launches that executable on the host machine.

The host executable prints or writes the TCP/IP port used for DUT communication.
When `--port=socket://localhost` is specified without a port number, the plugin is expected to read `port` from `*.host-arduino.json` under the build output directory and complete the actual connection URL.

```json
{
  "pid": 21228,
  "port": 56789
}
```

Expected command:

```bash
uv run pytest examples/09_host_arduino_core --profile host --port=socket://localhost
```

If the port number is already known, specify it explicitly:

```bash
uv run pytest examples/09_host_arduino_core --profile host --port=socket://localhost:56789
```

In that case, the plugin uses the socket URL as-is and does not complete the port number.
