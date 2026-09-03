"""Thermals: cross-platform CPU, GPU, SoC temperature and thermal-state readings.

    >>> import thermals
    >>> thermals.cpu_temperature()
    52.4
    >>> reading = thermals.cpu()
    >>> reading.kind, reading.source, reading.confidence
    (<SensorKind.CPU_PACKAGE: 'cpu_package'>, 'hwmon', <Confidence.HIGH: 'high'>)

Every reading carries its sensor kind, source backend and a confidence level
so that an ACPI thermal zone is never silently presented as the CPU package
temperature.
"""

from __future__ import annotations

from thermals.api import (
    CPU_KIND_PRIORITY,
    GPU_KIND_PRIORITY,
    backend,
    cpu,
    cpu_temperature,
    gpu,
    gpu_temperature,
    list_backends,
    select_reading,
    sensors,
    snapshot,
    thermal_state,
)
from thermals.exceptions import BackendError, BackendUnavailableError, ThermalsError
from thermals.models import (
    BackendInfo,
    Confidence,
    SensorKind,
    Snapshot,
    Stability,
    TemperatureReading,
    ThermalState,
)

__version__ = "0.1.0"

__all__ = [
    "CPU_KIND_PRIORITY",
    "GPU_KIND_PRIORITY",
    "BackendError",
    "BackendInfo",
    "BackendUnavailableError",
    "Confidence",
    "SensorKind",
    "Snapshot",
    "Stability",
    "TemperatureReading",
    "ThermalState",
    "ThermalsError",
    "__version__",
    "backend",
    "cpu",
    "cpu_temperature",
    "gpu",
    "gpu_temperature",
    "list_backends",
    "select_reading",
    "sensors",
    "snapshot",
    "thermal_state",
]
