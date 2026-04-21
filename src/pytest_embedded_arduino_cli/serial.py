from __future__ import annotations

from _pytest.config import Config
import os


def normalize_profile_name(profile: str) -> str:
    return profile.upper().replace("-", "_")


def ensure_default_embedded_services(config: Config) -> None:
    current = getattr(config.option, "embedded_services", None)
    if not current:
        config.option.embedded_services = "serial"
        return

    services = [service.strip() for service in current.split(",") if service.strip()]
    if "serial" in services:
        return

    services.append("serial")
    config.option.embedded_services = ",".join(services)


def resolve_port(config: Config, profile: str | None = None) -> str | None:
    flash_port = getattr(config.option, "flash_port", None)
    if flash_port:
        return flash_port

    port = getattr(config.option, "port", None)
    if port:
        return port

    if profile is None:
        profile = getattr(config.option, "profile", None)

    if profile:
        profile_port = os.getenv(f"TEST_SERIAL_PORT_{normalize_profile_name(profile)}")
        if profile_port:
            return profile_port

    return os.getenv("TEST_SERIAL_PORT")


def resolve_upload_port(config: Config, profile: str | None = None) -> str | None:
    return resolve_port(config, profile=profile)
