"""Linux ``/sys/class/thermal`` backend.

Thermal zones are what the kernel thermal framework sees. On x86 the
``x86_pkg_temp`` zone mirrors the CPU package sensor; ``acpitz`` zones are
firmware defined and may sit anywhere on the board.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

from thermals.backends.base import ThermalBackend
from thermals.models import Confidence, SensorKind, Stability, TemperatureReading
from thermals.utils.temperature import is_plausible, millidegrees_to_celsius

log = logging.getLogger("thermals.backends.thermal_zone")

DEFAULT_ROOT = Path("/sys/class/thermal")
SOURCE = "thermal_zone"


def classify_thermal_zone(zone_type: str) -> tuple[SensorKind, Confidence]:
    """Map a thermal zone ``type`` to a sensor kind and confidence."""
    t = zone_type.strip().lower()
    if t == "x86_pkg_temp":
        return SensorKind.CPU_PACKAGE, Confidence.MEDIUM
    if t == "acpitz":
        return SensorKind.THERMAL_ZONE, Confidence.LOW
    if t in {"cpu", "cpu-thermal", "cpu_thermal"} or t.startswith(("cpu-", "cpu_")):
        return SensorKind.CPU_DIE, Confidence.MEDIUM
    if t.startswith("soc"):
        return SensorKind.SOC, Confidence.MEDIUM
    if t.startswith("gpu"):
        return SensorKind.GPU, Confidence.MEDIUM
    return SensorKind.THERMAL_ZONE, Confidence.LOW


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        log.debug("cannot read %s: %s", path, exc)
        return None


class ThermalZoneBackend(ThermalBackend):
    """Enumerate ``thermal_zone*`` entries."""

    name: ClassVar[str] = "thermal_zone"
    stability: ClassVar[Stability] = Stability.STABLE
    platforms: ClassVar[tuple[str, ...]] = ("Linux",)

    def __init__(self, root: Path | str = DEFAULT_ROOT) -> None:
        self._root = Path(root)

    def _zones(self) -> list[Path]:
        if not self._root.is_dir():
            return []
        try:
            return sorted(
                (p for p in self._root.iterdir() if p.name.startswith("thermal_zone")),
                key=lambda p: int(p.name[len("thermal_zone") :] or 0),
            )
        except (OSError, ValueError) as exc:
            log.debug("cannot list %s: %s", self._root, exc)
            return []

    def available(self) -> bool:
        return any((zone / "temp").exists() for zone in self._zones())

    def detail(self) -> str | None:
        if not self._root.is_dir():
            return f"{self._root} does not exist"
        if not self.available():
            return f"no thermal zones under {self._root}"
        return None

    def sensors(self) -> list[TemperatureReading]:
        readings: list[TemperatureReading] = []
        for zone in self._zones():
            raw = _read_text(zone / "temp")
            if raw is None:
                continue
            try:
                value = millidegrees_to_celsius(raw)
            except ValueError:
                log.debug("non-numeric value in %s: %r", zone / "temp", raw)
                continue
            if not is_plausible(value):
                log.debug("implausible value %s in %s", value, zone)
                continue
            zone_type = _read_text(zone / "type") or zone.name
            kind, confidence = classify_thermal_zone(zone_type)
            readings.append(
                TemperatureReading(
                    value=value,
                    kind=kind,
                    source=SOURCE,
                    name=f"{zone_type} ({zone.name})",
                    confidence=confidence,
                )
            )
        return readings
