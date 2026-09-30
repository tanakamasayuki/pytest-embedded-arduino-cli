"""pytest-embedded integration for Arduino CLI based projects."""

from .monitor import MonitorTarget, is_monitor_url

__all__ = ["MonitorTarget", "__version__", "is_monitor_url"]

__version__ = "1.8.0"
