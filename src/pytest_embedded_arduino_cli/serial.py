from __future__ import annotations

from _pytest.config import Config


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


def resolve_upload_port(config: Config) -> str | None:
    flash_port = getattr(config.option, "flash_port", None)
    if flash_port:
        return flash_port

    return getattr(config.option, "port", None)
