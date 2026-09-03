"""macOS backends.

* :class:`ThermalPressureBackend` uses the public ``NSProcessInfo.thermalState``.
* :class:`AppleSMCBackend` reads the System Management Controller through IOKit
  (undocumented but long-lived interface; works on Intel and Apple Silicon).
* :class:`AppleSiliconHIDBackend` reads SoC die sensors through the private
  IOHIDEventSystemClient interface.
* :class:`PowermetricsBackend` parses ``powermetrics`` output when running as root.
"""

from thermals.backends.macos.apple_silicon import AppleSiliconHIDBackend
from thermals.backends.macos.powermetrics import PowermetricsBackend
from thermals.backends.macos.smc import AppleSMCBackend
from thermals.backends.macos.thermal_pressure import ThermalPressureBackend

__all__ = [
    "AppleSMCBackend",
    "AppleSiliconHIDBackend",
    "PowermetricsBackend",
    "ThermalPressureBackend",
]
