from pathlib import Path

from pytest_embedded_arduino_cli.app import ArduinoCliBuildConfig
from pytest_embedded_arduino_cli.flasher import ArduinoCliUploadConfig


def test_upload_command_uses_profile_and_port(tmp_path: Path) -> None:
    sketch_dir = tmp_path / "sample"
    build_config = ArduinoCliBuildConfig(
        sketch_dir=sketch_dir,
        sketch_yaml=sketch_dir / "sketch.yaml",
        build_path=sketch_dir / "build" / "esp32",
        profile="esp32",
    )

    upload_config = ArduinoCliUploadConfig.from_build_config(
        build_config,
        port="/dev/ttyUSB0",
        extra_args=("--verify",),
    )

    assert upload_config.upload_command() == [
        "arduino-cli",
        "upload",
        "--build-path",
        str(sketch_dir / "build" / "esp32"),
        "--profile",
        "esp32",
        "--port",
        "/dev/ttyUSB0",
        "--verify",
        str(sketch_dir),
    ]

