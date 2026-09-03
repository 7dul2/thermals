"""LibreHardwareMonitor backend for Windows.

Instead of loading ``LibreHardwareMonitorLib.dll`` in-process (which needs
pythonnet, a .NET runtime, administrator rights for the kernel driver and
redistribution of the DLL), this backend talks to an already running
LibreHardwareMonitor application:

1. its WMI provider in the ``root/LibreHardwareMonitor`` namespace, or
2. its optional HTTP server (``http://localhost:8085/data.json``).

Both transports are zero-dependency and license neutral. The URL can be
overridden with the ``THERMALS_LHM_URL`` environment variable.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request
from collections.abc import Callable
from typing import Any, ClassVar

from thermals.backends.base import ThermalBackend
from thermals.backends.windows._powershell import run_powershell
from thermals.models import Confidence, SensorKind, Stability, TemperatureReading
from thermals.utils.temperature import is_plausible, parse_float

log = logging.getLogger("thermals.backends.librehardwaremonitor")

SOURCE = "librehardwaremonitor"
DEFAULT_HTTP_URL = "http://localhost:8085/data.json"
ENV_HTTP_URL = "THERMALS_LHM_URL"
_CACHE_SECONDS = 0.5

WMI_SCRIPT = (
    "$hw = Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Hardware "
    "| Select-Object Identifier,Name,HardwareType; "
    "$se = Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor "
    "| Where-Object { $_.SensorType -eq 'Temperature' } "
    "| Select-Object Identifier,Name,Value,Parent; "
    "@{ hardware = @($hw); sensors = @($se) } | ConvertTo-Json -Compress -Depth 4"
)

# Hardware identifier prefixes used by LibreHardwareMonitor -> HardwareType names.
_IDENTIFIER_TYPES = {
    "intelcpu": "Cpu",
    "amdcpu": "Cpu",
    "cpu": "Cpu",
    "nvidiagpu": "GpuNvidia",
    "amdgpu": "GpuAmd",
    "intelgpu": "GpuIntel",
    "gpu": "Gpu",
    "lpc": "SuperIO",
    "motherboard": "Motherboard",
    "ram": "Memory",
    "nvme": "Storage",
    "hdd": "Storage",
    "ssd": "Storage",
    "battery": "Battery",
}


def hardware_type_from_identifier(identifier: str) -> str:
    """Infer the LibreHardwareMonitor hardware type from an identifier like ``/intelcpu/0``."""
    parts = [p for p in identifier.split("/") if p]
    if not parts:
        return "Unknown"
    return _IDENTIFIER_TYPES.get(parts[0].lower(), "Unknown")


def classify_lhm_sensor(
    hardware_type: str, sensor_name: str
) -> tuple[SensorKind, Confidence] | None:
    """Map a LibreHardwareMonitor temperature sensor to ``(kind, confidence)``.

    Returns ``None`` for entries that are not temperatures (``Distance to
    TjMax``) or aggregates that would duplicate other sensors (``Core Average``).
    """
    ht = hardware_type.strip().lower()
    n = sensor_name.strip().lower()
    if "distance to tjmax" in n or n.endswith("average"):
        return None

    if ht == "cpu":
        if n in {"cpu package", "package"} or n.startswith("cpu package"):
            return SensorKind.CPU_PACKAGE, Confidence.HIGH
        if "tctl/tdie" in n:
            return SensorKind.CPU_DIE, Confidence.HIGH
        if "tdie" in n:
            return SensorKind.CPU_DIE, Confidence.HIGH
        if "tctl" in n:
            return SensorKind.CPU_CONTROL, Confidence.HIGH
        if "ccd" in n:
            return SensorKind.CPU_DIE, Confidence.HIGH
        if n in {"core max", "cpu core max"} or "core #" in n or n.startswith("core "):
            return SensorKind.CPU_CORE, Confidence.HIGH
        if n.startswith("cpu core"):
            return SensorKind.CPU_CORE, Confidence.HIGH
        return SensorKind.UNKNOWN, Confidence.MEDIUM

    if ht.startswith("gpu"):
        if n in {"gpu core", "gpu", "gpu temperature"} or n.startswith("gpu core"):
            return SensorKind.GPU, Confidence.HIGH
        if "hot spot" in n or "hotspot" in n or "junction" in n:
            return SensorKind.GPU, Confidence.MEDIUM
        return SensorKind.UNKNOWN, Confidence.LOW

    if ht in {"motherboard", "superio", "embeddedcontroller"}:
        if n.startswith("cpu"):
            return SensorKind.CPU_PACKAGE, Confidence.LOW
        if n.startswith("gpu"):
            return SensorKind.GPU, Confidence.LOW
        return SensorKind.UNKNOWN, Confidence.LOW

    return SensorKind.UNKNOWN, Confidence.LOW


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_wmi_payload(text: str) -> list[TemperatureReading]:
    """Parse the JSON produced by :data:`WMI_SCRIPT`."""
    text = text.strip()
    if not text:
        return []
    payload = json.loads(text)
    hardware_by_id: dict[str, dict[str, Any]] = {}
    for hw in _as_list(payload.get("hardware")):
        if isinstance(hw, dict) and hw.get("Identifier"):
            hardware_by_id[str(hw["Identifier"])] = hw
    readings: list[TemperatureReading] = []
    for sensor in _as_list(payload.get("sensors")):
        if not isinstance(sensor, dict):
            continue
        parent = str(sensor.get("Parent") or "")
        hw = hardware_by_id.get(parent, {})
        hardware_type = str(hw.get("HardwareType") or hardware_type_from_identifier(parent))
        reading = _make_reading(hardware_type, str(sensor.get("Name") or ""), sensor.get("Value"))
        if reading is not None:
            readings.append(reading)
    return readings


def parse_http_payload(payload: dict[str, Any]) -> list[TemperatureReading]:
    """Parse the tree served by LibreHardwareMonitor's ``data.json`` endpoint."""
    readings: list[TemperatureReading] = []
    _walk_http_node(payload, readings)
    return readings


def _walk_http_node(node: dict[str, Any], readings: list[TemperatureReading]) -> None:
    sensor_id = node.get("SensorId")
    if sensor_id and node.get("Type") == "Temperature":
        hardware_type = hardware_type_from_identifier(str(sensor_id))
        reading = _make_reading(hardware_type, str(node.get("Text") or ""), node.get("Value"))
        if reading is not None:
            readings.append(reading)
        return
    for child in _as_list(node.get("Children")):
        if isinstance(child, dict):
            _walk_http_node(child, readings)


def _make_reading(hardware_type: str, name: str, raw_value: Any) -> TemperatureReading | None:
    classified = classify_lhm_sensor(hardware_type, name)
    if classified is None:
        return None
    if isinstance(raw_value, (int, float)):
        value: float | None = float(raw_value)
    else:
        value = parse_float(str(raw_value)) if raw_value is not None else None
    if value is None or not is_plausible(value):
        return None
    kind, confidence = classified
    return TemperatureReading(
        value=value, kind=kind, source=SOURCE, name=name, confidence=confidence
    )


def fetch_http_json(url: str, timeout: float = 3.0) -> dict[str, Any]:
    """Download and decode ``data.json``."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise RuntimeError("unexpected JSON payload")
    return data


class LibreHardwareMonitorBackend(ThermalBackend):
    """Sensors from a running LibreHardwareMonitor instance."""

    name: ClassVar[str] = "librehardwaremonitor"
    stability: ClassVar[Stability] = Stability.STABLE
    platforms: ClassVar[tuple[str, ...]] = ("Windows",)

    def __init__(
        self,
        wmi_runner: Callable[[str], str] | None = None,
        http_fetcher: Callable[[str], dict[str, Any]] | None = None,
        http_url: str | None = None,
    ) -> None:
        self._wmi_runner = wmi_runner
        self._http_fetcher = http_fetcher
        self._http_url = http_url or os.environ.get(ENV_HTTP_URL, DEFAULT_HTTP_URL)
        self._cache: tuple[float, list[TemperatureReading]] | None = None
        self._errors: list[str] = []
        self._transport: str | None = None

    def _fetch(self) -> list[TemperatureReading]:
        now = time.monotonic()
        if self._cache is not None and now - self._cache[0] < _CACHE_SECONDS:
            return self._cache[1]
        errors: list[str] = []
        readings: list[TemperatureReading] | None = None
        runner = self._wmi_runner or run_powershell
        try:
            readings = parse_wmi_payload(runner(WMI_SCRIPT))
            self._transport = "wmi"
        except Exception as exc:
            errors.append(f"WMI: {exc}")
            log.debug("LibreHardwareMonitor WMI query failed: %s", exc)
        if readings is None:
            fetcher = self._http_fetcher or fetch_http_json
            try:
                readings = parse_http_payload(fetcher(self._http_url))
                self._transport = "http"
            except Exception as exc:
                errors.append(f"HTTP {self._http_url}: {exc}")
                log.debug("LibreHardwareMonitor HTTP query failed: %s", exc)
        self._errors = errors
        if readings is None:
            self._transport = None
            raise RuntimeError("; ".join(errors))
        self._cache = (now, readings)
        return readings

    def available(self) -> bool:
        if self._wmi_runner is None and self._http_fetcher is None and sys.platform != "win32":
            self._errors = ["not running on Windows"]
            return False
        try:
            return bool(self._fetch())
        except Exception:
            return False

    def detail(self) -> str | None:
        if self._transport:
            return f"connected via {self._transport}"
        if self._errors == ["not running on Windows"]:
            return self._errors[0]
        hint = (
            "LibreHardwareMonitor is not running or not reachable. Start "
            "LibreHardwareMonitor (https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) "
            "or enable its Remote Web Server and set THERMALS_LHM_URL."
        )
        if self._errors:
            return f"{hint} ({'; '.join(self._errors)})"
        return hint

    def sensors(self) -> list[TemperatureReading]:
        try:
            return self._fetch()
        except Exception as exc:
            log.debug("LibreHardwareMonitor read failed: %s", exc)
            return []
