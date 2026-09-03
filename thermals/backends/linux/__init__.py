"""Linux backends: ``/sys/class/hwmon`` and ``/sys/class/thermal``."""

from thermals.backends.linux.hwmon import HwmonBackend
from thermals.backends.linux.thermal_zone import ThermalZoneBackend

__all__ = ["HwmonBackend", "ThermalZoneBackend"]
