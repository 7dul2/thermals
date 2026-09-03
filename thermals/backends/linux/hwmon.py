"""Linux ``/sys/class/hwmon`` backend.

Reads ``tempN_input`` / ``tempN_label`` files directly; ``lm-sensors`` is not
required. Values are millidegrees Celsius.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

from thermals.backends.base import ThermalBackend
from thermals.models import Confidence, SensorKind, Stability, TemperatureReading
from thermals.utils.temperature import is_plausible, millidegrees_to_celsius

log = logging.getLogger("thermals.backends.hwmon")

DEFAULT_ROOT = Path("/sys/class/hwmon")
SOURCE = "hwmon"

_GPU_CHIPS = {"amdgpu", "radeon", "nouveau", "i915", "xe"}
_ARM_CPU_CHIPS = {"cpu_thermal", "cpu-thermal", "bcm2835_thermal", "cpu"}
_ARM_SOC_CHIPS = {"soc_thermal", "soc-thermal", "soc"}


def classify_hwmon(chip: str, label: str | None) -> tuple[SensorKind, Confidence]:
    """Map a hwmon chip name and sensor label to a sensor kind and confidence."""
    chip_l = chip.strip().lower()
    label_l = (label or "").strip().lower()

    if chip_l == "coretemp":
        if label_l.startswith("package id") or label_l.startswith("physical id"):
            return SensorKind.CPU_PACKAGE, Confidence.HIGH
        if label_l.startswith("core"):
            return SensorKind.CPU_CORE, Confidence.HIGH
        return SensorKind.UNKNOWN, Confidence.MEDIUM

    if chip_l in {"k10temp", "zenpower"}:
        if label_l == "tctl":
            return SensorKind.CPU_CONTROL, Confidence.HIGH
        if label_l == "tdie" or label_l.startswith("tccd"):
            return SensorKind.CPU_DIE, Confidence.HIGH
        if not label_l:
            # Old k10temp exposes a single unlabeled temp1 which is Tctl.
            return SensorKind.CPU_CONTROL, Confidence.MEDIUM
        return SensorKind.UNKNOWN, Confidence.LOW

    if chip_l in _GPU_CHIPS:
        if label_l in {"", "edge", "gpu"}:
            return SensorKind.GPU, Confidence.HIGH
        if label_l in {"junction", "hotspot", "hot spot"}:
            return SensorKind.GPU, Confidence.MEDIUM
        return SensorKind.UNKNOWN, Confidence.LOW

    if chip_l in _ARM_CPU_CHIPS:
        return SensorKind.CPU_DIE, Confidence.MEDIUM
    if chip_l in _ARM_SOC_CHIPS:
        return SensorKind.SOC, Confidence.MEDIUM
    if chip_l == "acpitz":
        return SensorKind.THERMAL_ZONE, Confidence.LOW
    if chip_l.startswith(("pch_", "nvme", "drivetemp", "iwlwifi", "spd5118", "jc42")):
        return SensorKind.UNKNOWN, Confidence.LOW

    # Generic label heuristics for board/EC drivers (dell_smm, thinkpad, asus...).
    if "package" in label_l:
        return SensorKind.CPU_PACKAGE, Confidence.MEDIUM
    if "tdie" in label_l:
        return SensorKind.CPU_DIE, Confidence.MEDIUM
    if "tctl" in label_l:
        return SensorKind.CPU_CONTROL, Confidence.MEDIUM
    if label_l.startswith("gpu"):
        return SensorKind.GPU, Confidence.MEDIUM
    if label_l.startswith("core"):
        return SensorKind.CPU_CORE, Confidence.MEDIUM
    if label_l.startswith("cpu"):
        # Board-level "CPU" header: real CPU related, but not the die sensor.
        return SensorKind.CPU_PACKAGE, Confidence.LOW
    return SensorKind.UNKNOWN, Confidence.LOW


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        log.debug("cannot read %s: %s", path, exc)
        return None


class HwmonBackend(ThermalBackend):
    """Enumerate temperature sensors from ``/sys/class/hwmon``."""

    name: ClassVar[str] = "hwmon"
    stability: ClassVar[Stability] = Stability.STABLE
    platforms: ClassVar[tuple[str, ...]] = ("Linux",)

    def __init__(self, root: Path | str = DEFAULT_ROOT) -> None:
        self._root = Path(root)

    def _chip_dirs(self) -> list[Path]:
        if not self._root.is_dir():
            return []
        try:
            return sorted(p for p in self._root.iterdir() if p.name.startswith("hwmon"))
        except OSError as exc:
            log.debug("cannot list %s: %s", self._root, exc)
            return []

    @staticmethod
    def _sensor_dir(chip_dir: Path) -> Path:
        """Older kernels place the sensor files under ``device/``."""
        if any(chip_dir.glob("temp*_input")):
            return chip_dir
        device = chip_dir / "device"
        if device.is_dir() and any(device.glob("temp*_input")):
            return device
        return chip_dir

    def available(self) -> bool:
        return any(any(self._sensor_dir(chip).glob("temp*_input")) for chip in self._chip_dirs())

    def detail(self) -> str | None:
        if not self._root.is_dir():
            return f"{self._root} does not exist"
        if not self.available():
            return f"no temperature inputs under {self._root}"
        return None

    def sensors(self) -> list[TemperatureReading]:
        readings: list[TemperatureReading] = []
        for chip_dir in self._chip_dirs():
            sensor_dir = self._sensor_dir(chip_dir)
            chip = _read_text(sensor_dir / "name") or _read_text(chip_dir / "name") or chip_dir.name
            for input_path in sorted(sensor_dir.glob("temp*_input"), key=_temp_index):
                prefix = input_path.name[: -len("_input")]
                raw = _read_text(input_path)
                if raw is None:
                    continue
                try:
                    value = millidegrees_to_celsius(raw)
                except ValueError:
                    log.debug("non-numeric value in %s: %r", input_path, raw)
                    continue
                label = _read_text(sensor_dir / f"{prefix}_label")
                kind, confidence = classify_hwmon(chip, label)
                if not is_plausible(value):
                    log.debug("implausible value %s in %s", value, input_path)
                    continue
                readings.append(
                    TemperatureReading(
                        value=value,
                        kind=kind,
                        source=SOURCE,
                        name=f"{chip} {label or prefix}",
                        confidence=confidence,
                    )
                )
        return readings


def _temp_index(path: Path) -> int:
    digits = "".join(ch for ch in path.name if ch.isdigit())
    return int(digits) if digits else 0
