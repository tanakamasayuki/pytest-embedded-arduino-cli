from pathlib import Path

import pytest

from pytest_embedded_arduino_cli.app import (
    ArduinoCliBuildConfig,
    SketchConfigError,
    find_sketch_yaml,
    load_sketch_yaml,
    resolve_build_properties,
    resolve_build_path,
    resolve_profile_name,
    resolve_sketch_dir,
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

    with pytest.raises(SketchConfigError):
        resolve_profile_name(sketch_data, "mega")


def test_resolve_profile_name_rejects_ambiguous_profiles() -> None:
    sketch_data = {"profiles": {"esp32": {}, "esp32s3": {}}}

    with pytest.raises(SketchConfigError):
        resolve_profile_name(sketch_data, None)


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
