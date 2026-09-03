"""ACPI thermal zone fallback for Windows (``MSAcpi_ThermalZoneTemperature``).

ACPI thermal zones are defined by the firmware. They are often a chipset or
board sensor rather than the CPU, update slowly, and on some machines require
administrator rights. Readings are therefore ``THERMAL_ZONE`` / ``LOW``.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from typing import Any, ClassVar

from thermals.backends.base import ThermalBackend
from thermals.backends.windows._powershell import run_powershell
from thermals.models import Confidence, SensorKind, Stability, TemperatureReading
from thermals.utils.temperature import decikelvin_to_celsius, is_plausible

log = logging.getLogger("thermals.backends.acpi")

SOURCE = "acpi"

ACPI_SCRIPT = (
    "@(Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature "
    "| Select-Object InstanceName,CurrentTemperature) | ConvertTo-Json -Compress"
)


def parse_acpi_payload(text: str) -> list[TemperatureReading]:
    """Parse the JSON produced by :data:`ACPI_SCRIPT`."""
    text = text.strip()
    if not text:
        return []
    payload: Any = json.loads(text)
    entries = payload if isinstance(payload, list) else [payload]
    readings: list[TemperatureReading] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("CurrentTemperature")
        if not isinstance(raw, (int, float)):
            continue
        value = decikelvin_to_celsius(raw)
        # Firmware reports 2732 (~0 C) for absent zones; nothing real sits below 1 C.
        if value < 1.0 or not is_plausible(value):
            continue
        instance = str(entry.get("InstanceName") or "ACPI thermal zone")
        readings.append(
            TemperatureReading(
                value=round(value, 2),
                kind=SensorKind.THERMAL_ZONE,
                source=SOURCE,
                name=instance,
                confidence=Confidence.LOW,
            )
        )
    return readings


class ACPIThermalZoneBackend(ThermalBackend):
    """Low-confidence ACPI thermal zone readings."""

    name: ClassVar[str] = "acpi"
    stability: ClassVar[Stability] = Stability.STABLE
    platforms: ClassVar[tuple[str, ...]] = ("Windows",)

    def __init__(self, runner: Callable[[str], str] | None = None) -> None:
        self._runner = runner
        self._error: str | None = None

    def _read(self) -> list[TemperatureReading]:
        runner = self._runner or run_powershell
        return parse_acpi_payload(runner(ACPI_SCRIPT))

    def available(self) -> bool:
        if self._runner is None and sys.platform != "win32":
            self._error = "not running on Windows"
            return False
        try:
            readings = self._read()
        except Exception as exc:
            self._error = str(exc)
            log.debug("ACPI thermal zones unavailable: %s", exc)
            return False
        if not readings:
            self._error = "no ACPI thermal zones reported"
            return False
        self._error = None
        return True

    def detail(self) -> str | None:
        return self._error

    def sensors(self) -> list[TemperatureReading]:
        try:
            return self._read()
        except Exception as exc:
            log.debug("ACPI thermal zone read failed: %s", exc)
            return []
