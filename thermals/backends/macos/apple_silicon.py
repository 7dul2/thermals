"""Apple Silicon SoC sensors through the private IOHIDEventSystemClient API.

This is the same interface used by most open source Apple Silicon monitors.
It is private, so it may break with a macOS update; the backend is marked
experimental. Sensor names differ by chip generation:

* M1: ``PMU tdie1`` ... (die sensors), ``PMU TP..`` (power rails)
* M2 - M4: ``pACC MTR Temp Sensor..`` (P cores), ``eACC MTR Temp Sensor..``
  (E cores), ``GPU MTR Temp Sensor..``, ``PMGR SOC Die Temp Sensor..``
* M5 (macOS 26): ``PMU tdie1..``, ``PMU2 tdie1..`` only

Only die sensors that can be attributed to CPU or GPU are labelled as such;
everything else is reported as ``SOC`` or ``UNKNOWN``.
"""

from __future__ import annotations

import logging
import platform
import re
import sys
from collections.abc import Callable
from ctypes import c_double, c_int, c_int64, c_void_p
from typing import ClassVar

from thermals.backends.base import ThermalBackend
from thermals.backends.macos._cf import core_foundation, iokit
from thermals.exceptions import BackendUnavailableError
from thermals.models import Confidence, SensorKind, Stability, TemperatureReading

log = logging.getLogger("thermals.backends.apple_silicon")

SOURCE = "iohid"

kHIDPage_AppleVendor = 0xFF00  # noqa: N816
kHIDUsage_AppleVendor_TemperatureSensor = 5  # noqa: N816
kIOHIDEventTypeTemperature = 15  # noqa: N816
_TEMPERATURE_FIELD = kIOHIDEventTypeTemperature << 16

_PMU_DIE = re.compile(r"^PMU\d* tdie\d+$")
_PMU_DEV = re.compile(r"^PMU\d* tdev\d+$")
_PMU_CAL = re.compile(r"^PMU\d* tcal$")


def classify_hid_sensor(name: str) -> tuple[SensorKind, Confidence, str] | None:
    """Map an IOHID temperature sensor product name to ``(kind, confidence, label)``.

    Returns ``None`` for entries that are not temperatures of anything
    (calibration values).
    """
    if _PMU_CAL.match(name):
        return None
    if name.startswith("pACC MTR Temp"):
        return SensorKind.CPU_DIE, Confidence.MEDIUM, "CPU performance cluster"
    if name.startswith("eACC MTR Temp"):
        return SensorKind.CPU_DIE, Confidence.MEDIUM, "CPU efficiency cluster"
    if name.startswith("GPU MTR Temp"):
        return SensorKind.GPU, Confidence.MEDIUM, "GPU"
    if name.startswith(("PMGR SOC Die Temp", "SOC MTR Temp")):
        return SensorKind.SOC, Confidence.MEDIUM, "SoC die"
    if _PMU_DIE.match(name):
        return SensorKind.SOC, Confidence.MEDIUM, "SoC die (PMU)"
    if _PMU_DEV.match(name):
        return SensorKind.UNKNOWN, Confidence.LOW, "PMU device"
    if name.startswith("ANE MTR Temp"):
        return SensorKind.UNKNOWN, Confidence.LOW, "Neural Engine"
    if name.startswith("ISP MTR Temp"):
        return SensorKind.UNKNOWN, Confidence.LOW, "ISP"
    if name.startswith("NAND"):
        return SensorKind.UNKNOWN, Confidence.LOW, "Storage"
    if name.startswith("gas gauge"):
        return SensorKind.UNKNOWN, Confidence.LOW, "Battery"
    return SensorKind.UNKNOWN, Confidence.LOW, name


class HIDTemperatureReader:
    """Enumerates Apple vendor temperature sensors through IOHIDEventSystemClient."""

    def __init__(self) -> None:
        self._client: int | None = None
        self._product_key: int | None = None

    def _ensure_client(self) -> int:
        if self._client is not None:
            return self._client
        cf = core_foundation()
        lib = iokit()
        try:
            lib.IOHIDEventSystemClientCreate.restype = c_void_p
            lib.IOHIDEventSystemClientCreate.argtypes = [c_void_p]
            lib.IOHIDEventSystemClientSetMatching.restype = c_int
            lib.IOHIDEventSystemClientSetMatching.argtypes = [c_void_p, c_void_p]
            lib.IOHIDEventSystemClientCopyServices.restype = c_void_p
            lib.IOHIDEventSystemClientCopyServices.argtypes = [c_void_p]
            lib.IOHIDServiceClientCopyProperty.restype = c_void_p
            lib.IOHIDServiceClientCopyProperty.argtypes = [c_void_p, c_void_p]
            lib.IOHIDServiceClientCopyEvent.restype = c_void_p
            lib.IOHIDServiceClientCopyEvent.argtypes = [c_void_p, c_int64, c_int, c_int64]
            lib.IOHIDEventGetFloatValue.restype = c_double
            lib.IOHIDEventGetFloatValue.argtypes = [c_void_p, c_int64]
        except AttributeError as exc:  # symbol missing on this macOS
            raise BackendUnavailableError(f"IOHIDEventSystemClient API missing: {exc}") from exc
        client = lib.IOHIDEventSystemClientCreate(None)
        if not client:
            raise BackendUnavailableError("IOHIDEventSystemClientCreate returned NULL")
        matching = cf.dictionary(
            {
                "PrimaryUsagePage": kHIDPage_AppleVendor,
                "PrimaryUsage": kHIDUsage_AppleVendor_TemperatureSensor,
            }
        )
        lib.IOHIDEventSystemClientSetMatching(client, matching)
        cf.release(matching)
        self._client = int(client)
        self._product_key = cf.string("Product")
        return self._client

    def read(self) -> list[tuple[str, float]]:
        """Return ``(product name, temperature)`` pairs."""
        cf = core_foundation()
        lib = iokit()
        client = self._ensure_client()
        services = lib.IOHIDEventSystemClientCopyServices(client)
        if not services:
            return []
        out: list[tuple[str, float]] = []
        try:
            for index in range(cf.array_count(services)):
                service = cf.array_get(services, index)
                if service is None:
                    continue
                name_ref = lib.IOHIDServiceClientCopyProperty(service, self._product_key)
                name = cf.to_str(name_ref)
                cf.release(name_ref)
                if not name:
                    continue
                event = lib.IOHIDServiceClientCopyEvent(service, kIOHIDEventTypeTemperature, 0, 0)
                if not event:
                    continue
                value = float(lib.IOHIDEventGetFloatValue(event, _TEMPERATURE_FIELD))
                cf.release(event)
                out.append((name, value))
        finally:
            cf.release(services)
        return out


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


class AppleSiliconHIDBackend(ThermalBackend):
    """SoC temperature sensors on Apple Silicon (experimental, private API)."""

    name: ClassVar[str] = "apple_silicon"
    stability: ClassVar[Stability] = Stability.EXPERIMENTAL
    platforms: ClassVar[tuple[str, ...]] = ("Darwin",)

    def __init__(self, reader: Callable[[], list[tuple[str, float]]] | None = None) -> None:
        self._reader = reader
        self._hid: HIDTemperatureReader | None = None
        self._error: str | None = None

    def _read(self) -> list[tuple[str, float]]:
        if self._reader is not None:
            return self._reader()
        if self._hid is None:
            self._hid = HIDTemperatureReader()
        return self._hid.read()

    def available(self) -> bool:
        if self._reader is None and not is_apple_silicon():
            self._error = "requires Apple Silicon macOS"
            return False
        try:
            readings = self._read()
        except Exception as exc:
            self._error = str(exc)
            log.debug("IOHID sensors unavailable: %s", exc)
            return False
        if not readings:
            self._error = "no IOHID temperature sensors found"
            return False
        self._error = None
        return True

    def detail(self) -> str | None:
        return self._error

    def sensors(self) -> list[TemperatureReading]:
        readings: list[TemperatureReading] = []
        for name, value in self._read():
            classified = classify_hid_sensor(name)
            if classified is None:
                continue
            # Die sensors report 0 or strongly negative values when unpopulated.
            if value <= 0.0 or value > 150.0:
                log.debug("skipping IOHID sensor %r with implausible value %s", name, value)
                continue
            kind, confidence, label = classified
            readings.append(
                TemperatureReading(
                    value=value,
                    kind=kind,
                    source=SOURCE,
                    name=f"{label} ({name})" if label != name else name,
                    confidence=confidence,
                )
            )
        return readings
