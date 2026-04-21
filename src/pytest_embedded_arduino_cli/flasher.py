from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess

from .app import ArduinoCliBuildConfig


@dataclass(frozen=True)
class ArduinoCliUploadConfig:
    sketch_dir: Path
    build_path: Path
    profile: str | None = None
    port: str | None = None
    extra_args: tuple[str, ...] = field(default_factory=tuple)
    cli_path: str = "arduino-cli"

    @classmethod
    def from_build_config(
        cls,
        build_config: ArduinoCliBuildConfig,
        *,
        port: str | None = None,
        extra_args: tuple[str, ...] = (),
        cli_path: str | None = None,
    ) -> "ArduinoCliUploadConfig":
        return cls(
            sketch_dir=build_config.sketch_dir,
            build_path=build_config.build_path,
            profile=build_config.profile,
            port=port,
            extra_args=tuple(extra_args),
            cli_path=cli_path or build_config.cli_path,
        )

    def upload_command(self) -> list[str]:
        command = [self.cli_path, "upload", "--build-path", str(self.build_path)]
        if self.profile:
            command.extend(["--profile", self.profile])
        if self.port:
            command.extend(["--port", self.port])
        command.extend(self.extra_args)
        command.append(str(self.sketch_dir))
        return command

    def upload(self, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.upload_command(),
            check=check,
            cwd=self.sketch_dir,
            text=True,
        )

