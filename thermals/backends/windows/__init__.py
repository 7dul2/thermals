"""Windows backends.

* :class:`LibreHardwareMonitorBackend` attaches to a *running*
  LibreHardwareMonitor instance through its WMI provider or HTTP server.
* :class:`ACPIThermalZoneBackend` reads ``MSAcpi_ThermalZoneTemperature``
  as a low-confidence fallback.
"""

from thermals.backends.windows.acpi import ACPIThermalZoneBackend
from thermals.backends.windows.libre_hardware_monitor import LibreHardwareMonitorBackend

__all__ = ["ACPIThermalZoneBackend", "LibreHardwareMonitorBackend"]
