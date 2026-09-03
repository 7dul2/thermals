"""Data models shared by every backend and the public API.

The central design rule of thermals is that a temperature is never just a
number. Every reading carries *what* was measured (:class:`SensorKind`),
*where* it came from (``source``) and *how much the label can be trusted*
(:class:`Confidence`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "BackendInfo",
    "Confidence",
    "SensorKind",
    "Snapshot",
    "Stability",
    "TemperatureReading",
    "ThermalState",
]


class SensorKind(str, Enum):
    """What a temperature sensor physically measures.

    Backends must preserve the original meaning of a sensor instead of
    collapsing everything into "CPU temperature". An ACPI thermal zone, an AMD
    ``Tctl`` control value and an Intel package sensor are different things.
    """

    CPU_PACKAGE = "cpu_package"
    """Whole-CPU package sensor (Intel ``Package id 0``, LibreHardwareMonitor ``CPU Package``)."""

    CPU_CORE = "cpu_core"
    """A single CPU core sensor."""

    CPU_DIE = "cpu_die"
    """CPU die / chiplet sensor (AMD ``Tdie``/``Tccd``, Apple Silicon core cluster sensors)."""

    CPU_CONTROL = "cpu_control"
    """Control temperature used by firmware for fan curves (AMD ``Tctl``). May include an offset."""

    GPU = "gpu"
    """GPU sensor (edge / core temperature unless the name says otherwise)."""

    SOC = "soc"
    """System-on-chip die sensor that cannot be attributed to CPU or GPU specifically."""

    THERMAL_ZONE = "thermal_zone"
    """Firmware thermal zone (ACPI). Location is vendor defined and often *not* the CPU."""

    UNKNOWN = "unknown"
    """Sensor exists but its meaning could not be determined."""


_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


class Confidence(str, Enum):
    """How much the :class:`SensorKind` label of a reading can be trusted.

    Confidence describes the certainty that a reading really is what its
    ``kind`` claims, not the accuracy of the number itself.

    * ``HIGH``: the driver or provider documents the sensor semantics
      (Linux ``coretemp``, ``k10temp``, LibreHardwareMonitor CPU sensors).
    * ``MEDIUM``: the mapping relies on well-established but undocumented
      conventions (Apple SMC key prefixes, ``x86_pkg_temp`` thermal zones).
    * ``LOW``: the sensor location is vendor defined or guessed from a name
      (ACPI thermal zones, motherboard "CPU" headers).
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        """Numeric rank, higher is more trustworthy."""
        return _CONFIDENCE_RANK[self.value]

    def at_least(self, other: Confidence) -> bool:
        """Return ``True`` if this confidence is equal to or higher than ``other``."""
        return self.rank >= other.rank


class ThermalState(str, Enum):
    """System-wide thermal pressure.

    The names follow Apple's ``NSProcessInfo.thermalState`` levels so that
    readers of Apple documentation see the same words.
    """

    NOMINAL = "nominal"
    FAIR = "fair"
    SERIOUS = "serious"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

    @property
    def level(self) -> int:
        """Severity as an integer: nominal 0 ... critical 3, unknown -1."""
        return {"nominal": 0, "fair": 1, "serious": 2, "critical": 3}.get(self.value, -1)


class Stability(str, Enum):
    """Whether a backend relies on public, stable interfaces."""

    STABLE = "stable"
    EXPERIMENTAL = "experimental"
    """Depends on undocumented or private interfaces that an OS update may break."""


@dataclass(frozen=True)
class TemperatureReading:
    """A single temperature reading in degrees Celsius.

    ``value`` is ``None`` when the reading could not be obtained; ``reason``
    then explains why.
    """

    value: float | None
    kind: SensorKind
    source: str
    name: str | None = None
    confidence: Confidence = Confidence.LOW
    reason: str | None = None

    @property
    def unit(self) -> str:
        """Always ``"C"``. Use :attr:`fahrenheit` for a converted value."""
        return "C"

    @property
    def available(self) -> bool:
        """``True`` when :attr:`value` holds a number."""
        return self.value is not None

    @property
    def fahrenheit(self) -> float | None:
        """The value converted to degrees Fahrenheit, or ``None``."""
        if self.value is None:
            return None
        return self.value * 9.0 / 5.0 + 32.0

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation."""
        return {
            "temperature": self.value,
            "unit": self.unit,
            "kind": self.kind.value,
            "source": self.source,
            "name": self.name,
            "confidence": self.confidence.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BackendInfo:
    """Description of a backend and whether it can be used right now."""

    name: str
    available: bool
    stability: Stability
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation."""
        return {
            "name": self.name,
            "available": self.available,
            "stability": self.stability.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Snapshot:
    """Everything thermals knows about the system at one point in time."""

    cpu: TemperatureReading
    gpu: TemperatureReading
    thermal_state: ThermalState
    sensors: tuple[TemperatureReading, ...]
    backends: tuple[BackendInfo, ...]
    timestamp: float

    @property
    def backend(self) -> str | None:
        """Name of the primary (first available) backend, or ``None``."""
        for info in self.backends:
            if info.available:
                return info.name
        return None

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation."""
        return {
            "cpu": self.cpu.to_dict(),
            "gpu": self.gpu.to_dict(),
            "thermal_state": self.thermal_state.value,
            "backend": self.backend,
            "backends": [b.to_dict() for b in self.backends],
            "sensors": [s.to_dict() for s in self.sensors],
            "timestamp": self.timestamp,
        }
