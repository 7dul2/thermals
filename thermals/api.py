"""Public API.

Simple functions return plain floats (or ``None``); the richer functions
return :class:`~thermals.models.TemperatureReading` objects that carry the
sensor kind, source and confidence.
"""

from __future__ import annotations

import logging
import time

from thermals import detection
from thermals.models import (
    BackendInfo,
    Confidence,
    SensorKind,
    Snapshot,
    TemperatureReading,
    ThermalState,
)

log = logging.getLogger("thermals")

__all__ = [
    "CPU_KIND_PRIORITY",
    "GPU_KIND_PRIORITY",
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

CPU_KIND_PRIORITY: tuple[SensorKind, ...] = (
    SensorKind.CPU_PACKAGE,
    SensorKind.CPU_DIE,
    SensorKind.CPU_CORE,
    SensorKind.CPU_CONTROL,
    SensorKind.SOC,
    SensorKind.THERMAL_ZONE,
)
"""Order in which sensor kinds are considered for :func:`cpu`."""

GPU_KIND_PRIORITY: tuple[SensorKind, ...] = (SensorKind.GPU,)
"""Order in which sensor kinds are considered for :func:`gpu`."""

_NO_SENSORS = "No supported temperature sensor available"


def sensors() -> list[TemperatureReading]:
    """Every temperature reading from every available backend."""
    readings: list[TemperatureReading] = []
    for backend_obj in detection.available_backends():
        try:
            readings.extend(backend_obj.sensors())
        except Exception as exc:
            log.debug("backend %s failed to read sensors: %s", backend_obj.name, exc)
    return readings


def select_reading(
    readings: list[TemperatureReading],
    priority: tuple[SensorKind, ...],
    min_confidence: Confidence,
    component: str,
    source: str | None = None,
) -> TemperatureReading:
    """Pick the best reading for ``component`` following ``priority``.

    Kinds are tried in order. Within a kind the most trustworthy confidence
    tier is used and the hottest sensor of that tier wins (so per-core sensors
    yield the maximum core temperature, and a documented GPU edge sensor beats
    a heuristically labelled hotspot). Readings below ``min_confidence`` are
    ignored. When nothing qualifies, a reading with
    ``value=None`` and an explanatory ``reason`` is returned.
    """
    valid = [r for r in readings if r.value is not None]
    rejected: list[TemperatureReading] = []
    for kind in priority:
        candidates = [r for r in valid if r.kind == kind]
        accepted = [r for r in candidates if r.confidence.at_least(min_confidence)]
        if accepted:
            top = max(r.confidence.rank for r in accepted)
            tier = [r for r in accepted if r.confidence.rank == top]
            return max(tier, key=lambda r: r.value or float("-inf"))
        rejected.extend(candidates)

    if not valid:
        reason = _NO_SENSORS
    elif rejected:
        described = ", ".join(
            sorted({f"{r.kind.value}/{r.confidence.value} from {r.source}" for r in rejected})
        )
        reason = (
            f"Only low-confidence {component} sensors available ({described}); "
            f"pass min_confidence=Confidence.LOW to use them"
        )
    else:
        reason = f"No {component} temperature sensor found ({len(valid)} sensors of other kinds)"
    return TemperatureReading(
        value=None,
        kind=SensorKind.UNKNOWN,
        source=source or "none",
        name=None,
        confidence=Confidence.LOW,
        reason=reason,
    )


def _primary_source() -> str | None:
    return backend()


def cpu(min_confidence: Confidence = Confidence.MEDIUM) -> TemperatureReading:
    """The best available CPU temperature reading.

    Package sensors are preferred over die, core, control and SoC sensors;
    ACPI thermal zones are only used when ``min_confidence`` is ``LOW``.
    """
    return select_reading(sensors(), CPU_KIND_PRIORITY, min_confidence, "CPU", _primary_source())


def gpu(min_confidence: Confidence = Confidence.MEDIUM) -> TemperatureReading:
    """The best available GPU temperature reading."""
    return select_reading(sensors(), GPU_KIND_PRIORITY, min_confidence, "GPU", _primary_source())


def cpu_temperature(min_confidence: Confidence = Confidence.MEDIUM) -> float | None:
    """CPU temperature in Celsius, or ``None`` if no trustworthy sensor exists."""
    return cpu(min_confidence).value


def gpu_temperature(min_confidence: Confidence = Confidence.MEDIUM) -> float | None:
    """GPU temperature in Celsius, or ``None`` if no trustworthy sensor exists."""
    return gpu(min_confidence).value


def thermal_state() -> ThermalState:
    """System thermal pressure, ``UNKNOWN`` when no backend reports it."""
    for backend_obj in detection.available_backends():
        try:
            state = backend_obj.thermal_state()
        except Exception as exc:
            log.debug("backend %s failed to read thermal state: %s", backend_obj.name, exc)
            continue
        if state is not None:
            return state
    return ThermalState.UNKNOWN


def list_backends() -> list[BackendInfo]:
    """Describe every backend considered on this platform."""
    return [b.info() for b in detection.backends()]


def backend() -> str | None:
    """Name of the primary backend (first available), or ``None``."""
    available = detection.available_backends()
    return available[0].name if available else None


def snapshot(min_confidence: Confidence = Confidence.MEDIUM) -> Snapshot:
    """Read everything once and return a :class:`~thermals.models.Snapshot`.

    Sensors are read a single time, so this is the cheapest way to obtain CPU,
    GPU and thermal state together.
    """
    infos = tuple(list_backends())
    active = detection.available_backends()
    readings: list[TemperatureReading] = []
    state = ThermalState.UNKNOWN
    for backend_obj in active:
        try:
            readings.extend(backend_obj.sensors())
        except Exception as exc:
            log.debug("backend %s failed to read sensors: %s", backend_obj.name, exc)
        if state is ThermalState.UNKNOWN:
            try:
                reported = backend_obj.thermal_state()
            except Exception as exc:
                log.debug("backend %s failed to read thermal state: %s", backend_obj.name, exc)
                reported = None
            if reported is not None:
                state = reported
    primary = active[0].name if active else None
    return Snapshot(
        cpu=select_reading(readings, CPU_KIND_PRIORITY, min_confidence, "CPU", primary),
        gpu=select_reading(readings, GPU_KIND_PRIORITY, min_confidence, "GPU", primary),
        thermal_state=state,
        sensors=tuple(readings),
        backends=infos,
        timestamp=time.time(),
    )
