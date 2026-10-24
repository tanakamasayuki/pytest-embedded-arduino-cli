"""pytest-embedded integration for Arduino CLI based projects."""

from .monitor import MonitorTarget, is_monitor_url
from .combination import ArduinoCombination

__all__ = ["ArduinoCombination", "MonitorTarget", "__version__", "is_monitor_url"]

__version__ = "1.9.0"
