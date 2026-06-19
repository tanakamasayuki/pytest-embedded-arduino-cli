from pathlib import Path

import pytest

import subprocess

from pytest_embedded_arduino_cli.app import (
    ArduinoCliBuildConfig,
    SketchConfigError,
    UnsupportedProfileError,
    detect_build_property,
    detect_build_properties,
    find_sketch_yaml,
    load_sketch_yaml,
    parse_show_properties,
    resolve_build_flags,
    resolve_build_properties,
    resolve_build_path,
    resolve_profile_name,
    resolve_profile_port,
    resolve_sketch_dir,
    run_show_properties,
    select_build_property_override,
)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_resolve_sketch_dir_from_test_file(tmp_path: Path) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(sketch_dir / "sample.ino", "void setup() {}\nvoid loop() {}\n")
    write_text(sketch_dir / "test_sample.py", "def test_ok(): pass\n")

    assert resolve_sketch_dir(sketch_dir / "test_sample.py") == sketch_dir


def test_find_sketch_yaml_searches_parents(tmp_path: Path) -> None:
    root = tmp_path / "tests"
    sketch_dir = root / "sample"
    write_text(root / "sketch.yaml", "default_profile: uno\nprofiles:\n  uno: {}\n")
    write_text(sketch_dir / "sample.ino", "void setup() {}\nvoid loop() {}\n")

    assert find_sketch_yaml(sketch_dir) == root / "sketch.yaml"


def test_resolve_profile_name_uses_default_profile() -> None:
    sketch_data = {"default_profile": "esp32", "profiles": {"esp32": {}, "esp32s3": {}}}

    assert resolve_profile_name(sketch_data, None) == "esp32"


def test_resolve_profile_name_rejects_unknown_profile() -> None:
    sketch_data = {"profiles": {"uno": {}}}

    with pytest.raises(UnsupportedProfileError):
        resolve_profile_name(sketch_data, "mega")


def test_resolve_profile_name_rejects_ambiguous_profiles() -> None:
    sketch_data = {"profiles": {"esp32": {}, "esp32s3": {}}}

    with pytest.raises(SketchConfigError):
        resolve_profile_name(sketch_data, None)


def test_resolve_profile_port_reads_selected_profile_port() -> None:
    sketch_data = {
        "profiles": {
            "host": {"port": "socket://localhost"},
            "esp32": {"port": "/dev/ttyUSB0"},
        }
    }

    assert resolve_profile_port(sketch_data, "host") == "socket://localhost"


def test_resolve_profile_port_ignores_missing_or_non_string_port() -> None:
    assert resolve_profile_port({"profiles": {"host": {}}}, "host") is None
    assert resolve_profile_port({"profiles": {"host": {"port": 1234}}}, "host") is None
    assert resolve_profile_port({"profiles": {"host": {"port": "socket://localhost"}}}, None) is None


def test_default_build_path_uses_profile_name(tmp_path: Path) -> None:
    sketch_dir = tmp_path / "sample"

    assert resolve_build_path(sketch_dir, "esp32s3") == sketch_dir / "build" / "esp32s3"


def test_build_command_uses_profile_and_properties(tmp_path: Path) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(sketch_dir / "sample.ino", "void setup() {}\nvoid loop() {}\n")
    write_text(
        sketch_dir / "sketch.yaml",
        "default_profile: esp32\nprofiles:\n  esp32: {}\n",
    )

    config = ArduinoCliBuildConfig.from_test_path(
        sketch_dir / "test_sample.py",
        build_properties=("build.extra_flags=-DTEST=1",),
        extra_args=("--warnings", "all"),
        clean=True,
    )

    assert config.build_command() == [
        "arduino-cli",
        "compile",
        "--build-path",
        str(sketch_dir / "build" / "esp32"),
        "--clean",
        "--profile",
        "esp32",
        "--build-property",
        "build.extra_flags=-DTEST=1",
        "--warnings",
        "all",
        str(sketch_dir),
    ]


def test_missing_ino_is_rejected(tmp_path: Path) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(sketch_dir / "test_sample.py", "def test_ok(): pass\n")

    with pytest.raises(SketchConfigError):
        resolve_sketch_dir(sketch_dir / "test_sample.py")


def test_load_sketch_yaml_requires_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "sketch.yaml"
    write_text(config_path, "- not-a-mapping\n")

    with pytest.raises(SketchConfigError):
        load_sketch_yaml(config_path)


def test_resolve_build_properties_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(
        sketch_dir / "build_config.toml",
        '[defines]\nTEST_WIFI_SSID = "WIFI_SSID"\nTEST_WIFI_PASSWORD = "WIFI_PASSWORD"\n',
    )
    monkeypatch.setenv("TEST_WIFI_SSID", "my-ssid")
    monkeypatch.setenv("TEST_WIFI_PASSWORD", "my-password")

    assert resolve_build_properties(sketch_dir) == (
        'build.extra_flags=-DWIFI_SSID="my-ssid" -DWIFI_PASSWORD="my-password"',
    )


def test_resolve_build_properties_uses_empty_string_for_missing_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(
        sketch_dir / "build_config.toml",
        '[defines]\nTEST_WIFI_SSID = "WIFI_SSID"\nTEST_WIFI_PASSWORD = "WIFI_PASSWORD"\n',
    )
    monkeypatch.setenv("TEST_WIFI_SSID", "my-ssid")
    monkeypatch.delenv("TEST_WIFI_PASSWORD", raising=False)

    assert resolve_build_properties(sketch_dir) == (
        'build.extra_flags=-DWIFI_SSID="my-ssid" -DWIFI_PASSWORD=""',
    )


def test_resolve_build_properties_includes_enabled_flags(tmp_path: Path) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(
        sketch_dir / "build_config.toml",
        "[flags]\nPYTEST_BUILD = true\nDEBUG_TRACE = false\nENABLE_TEST_HOOKS = true\n",
    )

    assert resolve_build_properties(sketch_dir) == (
        "build.extra_flags=-DPYTEST_BUILD -DENABLE_TEST_HOOKS",
    )


def test_resolve_build_properties_combines_defines_and_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(
        sketch_dir / "build_config.toml",
        '[defines]\nTEST_API_URL = "API_URL"\n\n[flags]\nPYTEST_BUILD = true\n',
    )
    monkeypatch.setenv("TEST_API_URL", "https://example.test")

    assert resolve_build_properties(sketch_dir) == (
        'build.extra_flags=-DAPI_URL="https://example.test" -DPYTEST_BUILD',
    )


def test_load_build_config_rejects_non_mapping_flags(tmp_path: Path) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(sketch_dir / "build_config.toml", 'flags = ["PYTEST_BUILD"]\n')

    with pytest.raises(SketchConfigError):
        resolve_build_properties(sketch_dir)


def test_resolve_build_properties_rejects_non_boolean_flags(tmp_path: Path) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(sketch_dir / "build_config.toml", '[flags]\nPYTEST_BUILD = "yes"\n')

    with pytest.raises(SketchConfigError):
        resolve_build_properties(sketch_dir)


def test_build_command_includes_build_config_defines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(sketch_dir / "sample.ino", "void setup() {}\nvoid loop() {}\n")
    write_text(
        sketch_dir / "sketch.yaml",
        "default_profile: esp32\nprofiles:\n  esp32: {}\n",
    )
    write_text(
        sketch_dir / "build_config.toml",
        '[defines]\nTEST_WIFI_SSID = "WIFI_SSID"\n',
    )
    monkeypatch.setenv("TEST_WIFI_SSID", "test-ap")

    config = ArduinoCliBuildConfig.from_test_path(sketch_dir / "test_sample.py")

    assert config.build_command() == [
        "arduino-cli",
        "compile",
        "--build-path",
        str(sketch_dir / "build" / "esp32"),
        "--profile",
        "esp32",
        "--build-property",
        'build.extra_flags=-DWIFI_SSID="test-ap"',
        str(sketch_dir),
    ]


def test_resolve_build_flags_returns_raw_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(
        sketch_dir / "build_config.toml",
        '[defines]\nTEST_API_URL = "API_URL"\n\n[flags]\nPYTEST_BUILD = true\nOFF = false\n',
    )
    monkeypatch.setenv("TEST_API_URL", "https://example.test")

    assert resolve_build_flags(sketch_dir) == (
        '-DAPI_URL="https://example.test"',
        "-DPYTEST_BUILD",
    )


def test_resolve_build_properties_respects_build_property_arg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(sketch_dir / "build_config.toml", '[defines]\nTEST_SSID = "WIFI_SSID"\n')
    monkeypatch.setenv("TEST_SSID", "ap")

    assert resolve_build_properties(sketch_dir, build_property="build.defines") == (
        'build.defines=-DWIFI_SSID="ap"',
    )


def test_parse_show_properties_handles_empty_and_trailing_whitespace() -> None:
    text = "build.extra_flags=-DARDUINO=1 \r\nbuild.defines=\nbuild.core=esp32\nnoise line\n"
    props = parse_show_properties(text)

    assert props["build.extra_flags"] == "-DARDUINO=1"
    assert props["build.defines"] == ""
    assert props["build.core"] == "esp32"
    assert "noise line" not in props


def test_detect_build_property_picks_extra_flags_when_empty() -> None:
    props = {"build.extra_flags": "", "build.defines": ""}
    assert detect_build_property(props) == "build.extra_flags"
    assert detect_build_properties(props) == ("build.extra_flags",)


def test_detect_build_property_falls_back_to_defines_for_esp32() -> None:
    props = {"build.extra_flags": "-DARDUINO_USB_MODE=1", "build.defines": ""}
    assert detect_build_property(props) == "build.defines"
    assert detect_build_properties(props) == ("build.defines",)


def test_detect_build_properties_falls_back_to_c_and_cpp_extra_flags() -> None:
    props = {
        "build.extra_flags": "-DARDUINO_USB_MODE=1",
        "build.defines": "-DBOARD_HAS_PSRAM",
        "compiler.cpp.extra_flags": "",
        "compiler.c.extra_flags": "",
    }

    assert detect_build_properties(props) == ("compiler.cpp.extra_flags", "compiler.c.extra_flags")


def test_detect_build_properties_allows_cpp_only_fallback() -> None:
    props = {
        "build.extra_flags": "-DARDUINO_USB_MODE=1",
        "build.defines": "-DBOARD_HAS_PSRAM",
        "compiler.cpp.extra_flags": "",
        "compiler.c.extra_flags": "-DC_ONLY=1",
    }

    assert detect_build_properties(props) == ("compiler.cpp.extra_flags",)


def test_detect_build_property_raises_when_no_candidate_empty() -> None:
    props = {"build.extra_flags": "-DARDUINO_USB_MODE=1"}
    with pytest.raises(SketchConfigError) as exc:
        detect_build_properties(props)

    message = str(exc.value)
    assert "-DARDUINO_USB_MODE=1" in message
    assert "build.defines not present" in message
    assert "compiler.cpp.extra_flags not present" in message


def test_run_show_properties_uses_profile_and_parses(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="build.extra_flags=\n", stderr="")

    props = run_show_properties("arduino-cli", tmp_path, "esp32", runner=fake_runner)

    assert props == {"build.extra_flags": ""}
    assert captured["command"] == [
        "arduino-cli",
        "compile",
        "--show-properties",
        "--profile",
        "esp32",
        str(tmp_path),
    ]
    assert captured["kwargs"]["capture_output"] is True


def test_run_show_properties_omits_profile_when_none(tmp_path: Path) -> None:
    def fake_runner(command, **kwargs):
        assert "--profile" not in command
        return subprocess.CompletedProcess(command, 0, stdout="build.extra_flags=\n", stderr="")

    run_show_properties("arduino-cli", tmp_path, None, runner=fake_runner)


def test_select_build_property_override_precedence() -> None:
    config = {
        "build_property": "build.extra_flags",
        "profiles": {"esp32": {"build_property": "build.defines"}},
    }

    assert select_build_property_override(config, "esp32") == "build.defines"
    assert select_build_property_override(config, "uno") == "build.extra_flags"
    assert select_build_property_override({}, "esp32") is None


def test_select_build_property_override_rejects_non_string() -> None:
    with pytest.raises(SketchConfigError):
        select_build_property_override({"build_property": 1}, None)


def test_manual_override_applied_in_from_test_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(sketch_dir / "sample.ino", "void setup() {}\nvoid loop() {}\n")
    write_text(sketch_dir / "sketch.yaml", "default_profile: esp32\nprofiles:\n  esp32: {}\n")
    write_text(
        sketch_dir / "build_config.toml",
        '[profiles.esp32]\nbuild_property = "build.defines"\n\n[defines]\nTEST_SSID = "WIFI_SSID"\n',
    )
    monkeypatch.setenv("TEST_SSID", "ap")

    config = ArduinoCliBuildConfig.from_test_path(sketch_dir / "test_sample.py")

    assert config.manual_build_property == "build.defines"
    assert config.needs_build_property_detection() is False
    assert '--build-property' in config.build_command()
    assert 'build.defines=-DWIFI_SSID="ap"' in config.build_command()


def test_with_build_property_reformats_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(sketch_dir / "sample.ino", "void setup() {}\nvoid loop() {}\n")
    write_text(sketch_dir / "sketch.yaml", "default_profile: esp32\nprofiles:\n  esp32: {}\n")
    write_text(sketch_dir / "build_config.toml", '[defines]\nTEST_SSID = "WIFI_SSID"\n')
    monkeypatch.setenv("TEST_SSID", "ap")

    config = ArduinoCliBuildConfig.from_test_path(sketch_dir / "test_sample.py")
    assert config.needs_build_property_detection() is True

    switched = config.with_build_property("build.defines")
    assert switched.build_properties == ('build.defines=-DWIFI_SSID="ap"',)
    # original is unchanged (frozen dataclass)
    assert config.build_properties == ('build.extra_flags=-DWIFI_SSID="ap"',)


def test_with_build_properties_reformats_flags_for_multiple_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sketch_dir = tmp_path / "sample"
    write_text(sketch_dir / "sample.ino", "void setup() {}\nvoid loop() {}\n")
    write_text(sketch_dir / "sketch.yaml", "default_profile: esp32\nprofiles:\n  esp32: {}\n")
    write_text(sketch_dir / "build_config.toml", '[defines]\nTEST_SSID = "WIFI_SSID"\n')
    monkeypatch.setenv("TEST_SSID", "ap")

    config = ArduinoCliBuildConfig.from_test_path(sketch_dir / "test_sample.py")

    switched = config.with_build_properties(("compiler.cpp.extra_flags", "compiler.c.extra_flags"))

    assert switched.build_properties == (
        'compiler.cpp.extra_flags=-DWIFI_SSID="ap"',
        'compiler.c.extra_flags=-DWIFI_SSID="ap"',
    )
