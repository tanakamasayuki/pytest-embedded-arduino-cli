from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import os
import tomllib
from typing import Any

import yaml


class SketchConfigError(ValueError):
    """Raised when the sketch directory or sketch.yaml is invalid."""


class UnsupportedProfileError(SketchConfigError):
    """Raised when a requested profile is not supported by the sketch."""


def resolve_test_path(raw_path: str | Path) -> Path:
    path = Path(raw_path).resolve()
    if path.is_dir():
        return path
    return path.parent


def resolve_sketch_dir(test_file_or_dir: str | Path) -> Path:
    sketch_dir = resolve_test_path(test_file_or_dir)
    ino_files = sorted(sketch_dir.glob("*.ino"))
    if not ino_files:
        raise SketchConfigError(f"no .ino file found in sketch directory: {sketch_dir}")
    if len(ino_files) > 1:
        raise SketchConfigError(
            f"multiple .ino files found in sketch directory: {sketch_dir}. "
            "Keep one sketch per test directory."
        )
    return sketch_dir


def find_sketch_yaml(sketch_dir: str | Path) -> Path:
    current = Path(sketch_dir).resolve()
    for candidate_dir in (current, *current.parents):
        candidate = candidate_dir / "sketch.yaml"
        if candidate.is_file():
            return candidate
    raise SketchConfigError(f"sketch.yaml not found from sketch directory: {current}")


def load_sketch_yaml(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise SketchConfigError(f"sketch.yaml must contain a mapping: {config_path}")

    profiles = data.get("profiles", {})
    if profiles is not None and not isinstance(profiles, dict):
        raise SketchConfigError(f"'profiles' must be a mapping in {config_path}")

    return data


def resolve_profile_name(sketch_data: dict[str, Any], profile: str | None) -> str | None:
    profiles = sketch_data.get("profiles") or {}
    if profile:
        if profiles and profile not in profiles:
            raise UnsupportedProfileError(f"profile '{profile}' not found in sketch.yaml")
        return profile

    default_profile = sketch_data.get("default_profile")
    if default_profile is not None and not isinstance(default_profile, str):
        raise SketchConfigError("'default_profile' in sketch.yaml must be a string")

    if default_profile:
        return default_profile

    if len(profiles) == 1:
        return next(iter(profiles))

    if len(profiles) > 1:
        raise SketchConfigError(
            "multiple profiles found in sketch.yaml; "
            "specify --profile or set default_profile"
        )

    return None


def resolve_build_path(sketch_dir: str | Path, profile: str | None, build_path: str | Path | None = None) -> Path:
    if build_path:
        return Path(build_path).resolve()

    suffix = profile or "default"
    return Path(sketch_dir).resolve() / "build" / suffix


def load_build_config(sketch_dir: str | Path) -> dict[str, Any]:
    config_path = Path(sketch_dir).resolve() / "build_config.toml"
    if not config_path.is_file():
        return {}

    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    if not isinstance(data, dict):
        raise SketchConfigError(f"build_config.toml must contain a mapping: {config_path}")

    defines = data.get("defines", {})
    if defines is not None and not isinstance(defines, dict):
        raise SketchConfigError(f"'defines' must be a mapping in {config_path}")

    return data


def _format_define_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def resolve_build_properties(
    sketch_dir: str | Path,
    build_config: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    config = build_config if build_config is not None else load_build_config(sketch_dir)
    defines = config.get("defines") or {}
    extra_flags: list[str] = []

    for env_name, define_name in defines.items():
        if not isinstance(env_name, str) or not isinstance(define_name, str):
            raise SketchConfigError("build_config.toml defines keys and values must be strings")

        value = os.getenv(env_name, "")
        extra_flags.append(f"-D{define_name}={_format_define_value(value)}")

    if not extra_flags:
        return ()

    return (f"build.extra_flags={' '.join(extra_flags)}",)


@dataclass(frozen=True)
class ArduinoCliBuildConfig:
    sketch_dir: Path
    sketch_yaml: Path
    build_path: Path
    profile: str | None = None
    build_properties: tuple[str, ...] = field(default_factory=tuple)
    extra_args: tuple[str, ...] = field(default_factory=tuple)
    clean: bool = False
    cli_path: str = "arduino-cli"

    @classmethod
    def from_test_path(
        cls,
        test_file_or_dir: str | Path,
        *,
        profile: str | None = None,
        build_path: str | Path | None = None,
        build_properties: tuple[str, ...] = (),
        extra_args: tuple[str, ...] = (),
        clean: bool = False,
        cli_path: str = "arduino-cli",
    ) -> "ArduinoCliBuildConfig":
        sketch_dir = resolve_sketch_dir(test_file_or_dir)
        sketch_yaml = find_sketch_yaml(sketch_dir)
        sketch_data = load_sketch_yaml(sketch_yaml)
        build_config = load_build_config(sketch_dir)
        resolved_profile = resolve_profile_name(sketch_data, profile)
        resolved_build_path = resolve_build_path(sketch_dir, resolved_profile, build_path)
        resolved_build_properties = tuple(build_properties) + resolve_build_properties(sketch_dir, build_config)
        return cls(
            sketch_dir=sketch_dir,
            sketch_yaml=sketch_yaml,
            build_path=resolved_build_path,
            profile=resolved_profile,
            build_properties=resolved_build_properties,
            extra_args=tuple(extra_args),
            clean=clean,
            cli_path=cli_path,
        )

    def build_command(self) -> list[str]:
        command = [self.cli_path, "compile", "--build-path", str(self.build_path)]
        if self.clean:
            command.append("--clean")
        if self.profile:
            command.extend(["--profile", self.profile])
        for build_property in self.build_properties:
            command.extend(["--build-property", build_property])
        command.extend(self.extra_args)
        command.append(str(self.sketch_dir))
        return command

    def compile(self, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.build_command(),
            check=check,
            cwd=self.sketch_dir,
            text=True,
        )
