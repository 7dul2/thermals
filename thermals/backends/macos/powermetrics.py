"""``powermetrics`` backend (root only).

``powermetrics`` needs root, so this backend is only available when the
process runs as root. On Intel Macs it reports CPU/GPU die temperatures; on
Apple Silicon it reports thermal pressure only.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from typing import ClassVar

from thermals.backends.base import ThermalBackend
from thermals.models import Confidence, SensorKind, Stability, TemperatureReading, ThermalState
from thermals.utils.temperature import is_plausible

log = logging.getLogger("thermals.backends.powermetrics")

SOURCE = "powermetrics"

_DIE_TEMP = re.compile(r"^(CPU|GPU) die temperature:\s*([-+]?\d+(?:\.\d+)?)\s*C", re.MULTILINE)
_PRESSURE = re.compile(r"^Current pressure level:\s*(\w+)", re.MULTILINE)

PRESSURE_LEVELS: dict[str, ThermalState] = {
    "nominal": ThermalState.NOMINAL,
    "moderate": ThermalState.FAIR,
    "heavy": ThermalState.SERIOUS,
    "trapping": ThermalState.CRITICAL,
    "sleeping": ThermalState.CRITICAL,
}


def parse_powermetrics(text: str) -> tuple[list[TemperatureReading], ThermalState | None]:
    """Parse ``powermetrics`` output into readings and a thermal state."""
    readings: list[TemperatureReading] = []
    for component, value_text in _DIE_TEMP.findall(text):
        value = float(value_text)
        if not is_plausible(value):
            continue
        kind = SensorKind.CPU_DIE if component == "CPU" else SensorKind.GPU
        readings.append(
            TemperatureReading(
                value=value,
                kind=kind,
                source=SOURCE,
                name=f"{component} die temperature",
                confidence=Confidence.MEDIUM,
            )
        )
    state: ThermalState | None = None
    match = _PRESSURE.search(text)
    if match:
        state = PRESSURE_LEVELS.get(match.group(1).lower(), ThermalState.UNKNOWN)
    return readings, state


def _is_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return geteuid is not None and geteuid() == 0


def _precondition() -> str | None:
    """Why ``powermetrics`` cannot run here, or ``None`` if it can."""
    if platform.system() != "Darwin":
        return "not running on macOS"
    if not _is_root():
        return "powermetrics requires root"
    if shutil.which("powermetrics") is None:
        return "powermetrics binary not found"
    return None


def run_powermetrics(samplers: str = "thermal,smc") -> str:
    """Run ``powermetrics`` once and return its stdout."""
    exe = shutil.which("powermetrics") or "/usr/bin/powermetrics"
    result = subprocess.run(
        [exe, "--samplers", samplers, "-i", "200", "-n", "1"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        # Unknown samplers fail hard; retry with thermal only (Apple Silicon).
        if samplers != "thermal":
            return run_powermetrics("thermal")
        raise RuntimeError(result.stderr.strip() or f"powermetrics exited {result.returncode}")
    return result.stdout


class PowermetricsBackend(ThermalBackend):
    """Root-only backend parsing ``powermetrics`` output."""

    name: ClassVar[str] = "powermetrics"
    stability: ClassVar[Stability] = Stability.EXPERIMENTAL
    platforms: ClassVar[tuple[str, ...]] = ("Darwin",)

    def __init__(self, runner: Callable[[], str] | None = None) -> None:
        self._runner = runner
        self._error: str | None = None
        self._cache: tuple[list[TemperatureReading], ThermalState | None] | None = None

    def _run(self) -> tuple[list[TemperatureReading], ThermalState | None]:
        if self._runner is not None:
            return parse_powermetrics(self._runner())
        return parse_powermetrics(run_powermetrics())

    def available(self) -> bool:
        if self._runner is None:
            problem = _precondition()
            if problem is not None:
                self._error = problem
                return False
        try:
            self._cache = self._run()
        except Exception as exc:
            self._error = str(exc)
            log.debug("powermetrics unavailable: %s", exc)
            return False
        self._error = None
        return True

    def detail(self) -> str | None:
        return self._error

    def sensors(self) -> list[TemperatureReading]:
        try:
            self._cache = self._run()
        except Exception as exc:
            log.debug("powermetrics read failed: %s", exc)
            return []
        return self._cache[0]

    def thermal_state(self) -> ThermalState | None:
        if self._cache is None:
            try:
                self._cache = self._run()
            except Exception as exc:
                log.debug("powermetrics read failed: %s", exc)
                return None
        return self._cache[1]
