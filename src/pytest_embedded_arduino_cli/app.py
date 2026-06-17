from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import subprocess
import os
import tomllib
from typing import Any, Callable

import yaml


#: Default property used to inject build_config.toml defines/flags when no
#: explicit override is given and auto-detection has not run.
DEFAULT_BUILD_PROPERTY = "build.extra_flags"

#: Auto-detection candidates, in priority order. The first candidate that
#: exists and is empty for the target is used. On host / AVR boards
#: ``build.extra_flags`` is empty; on ESP32 it is platform-populated, so the
#: empty ``build.defines`` is selected instead.
BUILD_PROPERTY_CANDIDATES = ("build.extra_flags", "build.defines")


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


def resolve_profile_name(
    sketch_data: dict[str, Any],
    profile: str | None,
    *,
    allow_single_profile: bool = True,
) -> str | None:
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

    if allow_single_profile and len(profiles) == 1:
        return next(iter(profiles))

    if len(profiles) > 1:
        raise SketchConfigError(
            "multiple profiles found in sketch.yaml; "
            "specify --profile or set default_profile"
        )

    return None


def resolve_profile_port(sketch_data: dict[str, Any], profile: str | None) -> str | None:
    if profile is None:
        return None

    profiles = sketch_data.get("profiles") or {}
    profile_data = profiles.get(profile)
    if not isinstance(profile_data, dict):
        return None

    port = profile_data.get("port")
    if not isinstance(port, str):
        return None

    return port


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

    flags = data.get("flags", {})
    if flags is not None and not isinstance(flags, dict):
        raise SketchConfigError(f"'flags' must be a mapping in {config_path}")

    return data


def _format_define_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def resolve_build_flags(
    sketch_dir: str | Path,
    build_config: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    """Return the raw ``-D...`` tokens from build_config.toml defines/flags."""
    config = build_config if build_config is not None else load_build_config(sketch_dir)
    defines = config.get("defines") or {}
    flag_tokens: list[str] = []

    for env_name, define_name in defines.items():
        if not isinstance(env_name, str) or not isinstance(define_name, str):
            raise SketchConfigError("build_config.toml defines keys and values must be strings")

        value = os.getenv(env_name, "")
        flag_tokens.append(f"-D{define_name}={_format_define_value(value)}")

    flags = config.get("flags") or {}
    for flag_name, enabled in flags.items():
        if not isinstance(flag_name, str) or not isinstance(enabled, bool):
            raise SketchConfigError(
                "build_config.toml flags keys must be strings and values must be booleans"
            )
        if enabled:
            flag_tokens.append(f"-D{flag_name}")

    return tuple(flag_tokens)


def format_build_property(
    flags: tuple[str, ...],
    build_property: str = DEFAULT_BUILD_PROPERTY,
) -> tuple[str, ...]:
    """Wrap raw ``-D`` tokens into a single ``<property>=...`` build property."""
    if not flags:
        return ()
    return (f"{build_property}={' '.join(flags)}",)


def resolve_build_properties(
    sketch_dir: str | Path,
    build_config: dict[str, Any] | None = None,
    *,
    build_property: str = DEFAULT_BUILD_PROPERTY,
) -> tuple[str, ...]:
    return format_build_property(resolve_build_flags(sketch_dir, build_config), build_property)


def select_build_property_override(
    build_config: dict[str, Any] | None,
    profile: str | None,
) -> str | None:
    """Return the explicit build_property override, per-profile first then top-level."""
    config = build_config or {}

    if profile is not None:
        profiles = config.get("profiles") or {}
        profile_data = profiles.get(profile)
        if isinstance(profile_data, dict) and "build_property" in profile_data:
            value = profile_data["build_property"]
            if not isinstance(value, str) or not value:
                raise SketchConfigError(
                    "build_config.toml [profiles.*].build_property must be a non-empty string"
                )
            return value

    if "build_property" in config:
        value = config["build_property"]
        if not isinstance(value, str) or not value:
            raise SketchConfigError("build_config.toml build_property must be a non-empty string")
        return value

    return None


def parse_show_properties(text: str) -> dict[str, str]:
    """Parse ``arduino-cli compile --show-properties`` output into a dict."""
    properties: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        properties[key.strip()] = value.strip()
    return properties


def detect_build_property(
    properties: dict[str, str],
    candidates: tuple[str, ...] = BUILD_PROPERTY_CANDIDATES,
) -> str:
    """Pick the first candidate property that exists and is empty.

    Raises SketchConfigError if none qualify, so a clobbering build fails
    early with a clear message instead of a cryptic compile error.
    """
    for candidate in candidates:
        if candidate in properties and properties[candidate] == "":
            return candidate

    states = []
    for candidate in candidates:
        if candidate not in properties:
            states.append(f"{candidate} not present")
        else:
            states.append(f"{candidate} is non-empty ({properties[candidate]!r})")
    raise SketchConfigError(
        "cannot auto-select a build property for build_config.toml defines/flags; "
        f"{', '.join(states)}. Set 'build_property' in build_config.toml "
        "(top-level or under [profiles.<profile>]) to choose explicitly."
    )


def run_show_properties(
    cli_path: str,
    sketch_dir: str | Path,
    profile: str | None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, str]:
    """Probe the resolved (expanded) build properties for a sketch/profile."""
    command = [cli_path, "compile", "--show-properties"]
    if profile:
        command.extend(["--profile", profile])
    command.append(str(sketch_dir))
    result = runner(command, cwd=sketch_dir, text=True, capture_output=True, check=True)
    return parse_show_properties(result.stdout)


@dataclass(frozen=True)
class ArduinoCliBuildConfig:
    sketch_dir: Path
    sketch_yaml: Path
    build_path: Path
    profile: str | None = None
    profile_port: str | None = None
    build_properties: tuple[str, ...] = field(default_factory=tuple)
    extra_args: tuple[str, ...] = field(default_factory=tuple)
    clean: bool = False
    cli_path: str = "arduino-cli"
    build_flags: tuple[str, ...] = field(default_factory=tuple)
    build_property: str = DEFAULT_BUILD_PROPERTY
    manual_build_property: str | None = None
    extra_build_properties: tuple[str, ...] = field(default_factory=tuple)

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
        allow_single_profile: bool = True,
    ) -> "ArduinoCliBuildConfig":
        sketch_dir = resolve_sketch_dir(test_file_or_dir)
        sketch_yaml = find_sketch_yaml(sketch_dir)
        sketch_data = load_sketch_yaml(sketch_yaml)
        build_config = load_build_config(sketch_dir)
        resolved_profile = resolve_profile_name(
            sketch_data,
            profile,
            allow_single_profile=allow_single_profile,
        )
        resolved_profile_port = resolve_profile_port(sketch_data, resolved_profile)
        resolved_build_path = resolve_build_path(sketch_dir, resolved_profile, build_path)
        build_flags = resolve_build_flags(sketch_dir, build_config)
        manual_build_property = select_build_property_override(build_config, resolved_profile)
        chosen_property = manual_build_property or DEFAULT_BUILD_PROPERTY
        extra = tuple(build_properties)
        resolved_build_properties = extra + format_build_property(build_flags, chosen_property)
        return cls(
            sketch_dir=sketch_dir,
            sketch_yaml=sketch_yaml,
            build_path=resolved_build_path,
            profile=resolved_profile,
            profile_port=resolved_profile_port,
            build_properties=resolved_build_properties,
            extra_args=tuple(extra_args),
            clean=clean,
            cli_path=cli_path,
            build_flags=build_flags,
            build_property=chosen_property,
            manual_build_property=manual_build_property,
            extra_build_properties=extra,
        )

    def needs_build_property_detection(self) -> bool:
        """True when there are flags to inject and no explicit override was set."""
        return bool(self.build_flags) and self.manual_build_property is None

    def with_build_property(self, name: str) -> "ArduinoCliBuildConfig":
        """Return a copy that injects build_flags into the given property."""
        return replace(
            self,
            build_property=name,
            build_properties=self.extra_build_properties + format_build_property(self.build_flags, name),
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
