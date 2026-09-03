from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import load_json, load_text
from thermals import detection
from thermals.api import cpu, gpu, sensors
from thermals.backends.windows.libre_hardware_monitor import (
    WMI_SCRIPT,
    LibreHardwareMonitorBackend,
    classify_lhm_sensor,
    hardware_type_from_identifier,
    parse_http_payload,
    parse_wmi_payload,
)
from thermals.models import Confidence, SensorKind


def test_parse_wmi_intel() -> None:
    readings = {r.name: r for r in parse_wmi_payload(load_text("windows/lhm_wmi_intel.json"))}
    assert readings["CPU Package"].kind is SensorKind.CPU_PACKAGE
    assert readings["CPU Package"].confidence is Confidence.HIGH
    assert readings["CPU Package"].value == 57.0
    assert readings["CPU Core #1"].kind is SensorKind.CPU_CORE
    assert readings["Core Max"].kind is SensorKind.CPU_CORE
    assert "Core Average" not in readings
    assert "CPU Core #1 Distance to TjMax" not in readings
    assert readings["GPU Core"].kind is SensorKind.GPU
    assert readings["GPU Core"].confidence is Confidence.HIGH
    assert readings["GPU Hot Spot"].confidence is Confidence.MEDIUM
    assert readings["CPU"].kind is SensorKind.CPU_PACKAGE
    assert readings["CPU"].confidence is Confidence.LOW
    assert readings["System"].kind is SensorKind.UNKNOWN
    assert readings["Temperature"].kind is SensorKind.UNKNOWN
    assert all(r.source == "librehardwaremonitor" for r in readings.values())


def test_parse_wmi_amd() -> None:
    readings = {r.name: r for r in parse_wmi_payload(load_text("windows/lhm_wmi_amd.json"))}
    assert readings["Core (Tctl/Tdie)"].kind is SensorKind.CPU_DIE
    assert readings["CCD1 (Tdie)"].kind is SensorKind.CPU_DIE
    assert readings["GPU Memory"].kind is SensorKind.UNKNOWN
    assert readings["GPU Hot Spot"].kind is SensorKind.GPU


def test_parse_wmi_single_object_payload() -> None:
    [reading] = parse_wmi_payload(load_text("windows/lhm_wmi_single.json"))
    assert reading.kind is SensorKind.CPU_PACKAGE
    assert reading.value == 49.5


def test_parse_wmi_empty() -> None:
    assert parse_wmi_payload("") == []
    assert parse_wmi_payload("   \n") == []


def test_parse_http_tree() -> None:
    readings = {r.name: r for r in parse_http_payload(load_json("windows/lhm_http_data.json"))}
    assert set(readings) == {"CPU Core #1", "CPU Package", "GPU Core"}
    assert readings["CPU Core #1"].value == 55.0  # "55,0 °C" locale string
    assert readings["CPU Package"].kind is SensorKind.CPU_PACKAGE
    assert readings["GPU Core"].kind is SensorKind.GPU


def test_backend_with_wmi_runner() -> None:
    calls: list[str] = []

    def runner(script: str) -> str:
        calls.append(script)
        return load_text("windows/lhm_wmi_intel.json")

    backend = LibreHardwareMonitorBackend(wmi_runner=runner)
    assert backend.available()
    assert backend.detail() == "connected via wmi"
    assert calls == [WMI_SCRIPT]
    detection.set_backends([backend])
    assert cpu().name == "CPU Package"
    assert gpu().value == 43.0
    # cached: a second read inside the cache window does not rerun PowerShell
    assert len(sensors()) == 9
    assert len(calls) == 1


def test_backend_falls_back_to_http() -> None:
    def failing_wmi(script: str) -> str:
        raise RuntimeError("Invalid namespace")

    def fetcher(url: str) -> dict[str, Any]:
        assert url == "http://example.test/data.json"
        data: dict[str, Any] = load_json("windows/lhm_http_data.json")
        return data

    backend = LibreHardwareMonitorBackend(
        wmi_runner=failing_wmi, http_fetcher=fetcher, http_url="http://example.test/data.json"
    )
    assert backend.available()
    assert backend.detail() == "connected via http"
    assert {r.name for r in backend.sensors()} == {"CPU Core #1", "CPU Package", "GPU Core"}


def test_backend_unavailable_explains_how_to_fix() -> None:
    def failing_wmi(script: str) -> str:
        raise RuntimeError("Invalid namespace")

    def failing_http(url: str) -> dict[str, Any]:
        raise OSError("connection refused")

    backend = LibreHardwareMonitorBackend(wmi_runner=failing_wmi, http_fetcher=failing_http)
    assert not backend.available()
    assert backend.sensors() == []
    detail = backend.detail() or ""
    assert "LibreHardwareMonitor is not running" in detail
    assert "Invalid namespace" in detail
    assert "connection refused" in detail
    assert "THERMALS_LHM_URL" in detail


def test_backend_unavailable_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("thermals.backends.windows.libre_hardware_monitor.sys.platform", "linux")
    backend = LibreHardwareMonitorBackend()
    assert not backend.available()
    assert backend.detail() == "not running on Windows"


def test_http_url_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THERMALS_LHM_URL", "http://10.0.0.5:8085/data.json")
    seen: list[str] = []

    def failing_wmi(script: str) -> str:
        raise RuntimeError("no")

    def fetcher(url: str) -> dict[str, Any]:
        seen.append(url)
        data: dict[str, Any] = load_json("windows/lhm_http_data.json")
        return data

    backend = LibreHardwareMonitorBackend(wmi_runner=failing_wmi, http_fetcher=fetcher)
    assert backend.available()
    assert seen == ["http://10.0.0.5:8085/data.json"]


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("/intelcpu/0", "Cpu"),
        ("/amdcpu/0/temperature/1", "Cpu"),
        ("/nvidiagpu/0", "GpuNvidia"),
        ("/amdgpu/0", "GpuAmd"),
        ("/intelgpu/0", "GpuIntel"),
        ("/lpc/nct6798d/0", "SuperIO"),
        ("/nvme/0", "Storage"),
        ("", "Unknown"),
        ("/whatever/1", "Unknown"),
    ],
)
def test_hardware_type_from_identifier(identifier: str, expected: str) -> None:
    assert hardware_type_from_identifier(identifier) == expected


@pytest.mark.parametrize(
    ("hardware_type", "name", "expected"),
    [
        ("Cpu", "CPU Package", (SensorKind.CPU_PACKAGE, Confidence.HIGH)),
        ("Cpu", "CPU Core #3", (SensorKind.CPU_CORE, Confidence.HIGH)),
        ("Cpu", "Core Max", (SensorKind.CPU_CORE, Confidence.HIGH)),
        ("Cpu", "Core Average", None),
        ("Cpu", "CPU Core #1 Distance to TjMax", None),
        ("Cpu", "Core (Tctl/Tdie)", (SensorKind.CPU_DIE, Confidence.HIGH)),
        ("Cpu", "Core (Tctl)", (SensorKind.CPU_CONTROL, Confidence.HIGH)),
        ("Cpu", "CCD2 (Tdie)", (SensorKind.CPU_DIE, Confidence.HIGH)),
        ("Cpu", "Something", (SensorKind.UNKNOWN, Confidence.MEDIUM)),
        ("GpuNvidia", "GPU Core", (SensorKind.GPU, Confidence.HIGH)),
        ("GpuAmd", "GPU Hot Spot", (SensorKind.GPU, Confidence.MEDIUM)),
        ("GpuAmd", "GPU Memory", (SensorKind.UNKNOWN, Confidence.LOW)),
        ("SuperIO", "CPU", (SensorKind.CPU_PACKAGE, Confidence.LOW)),
        ("Motherboard", "GPU", (SensorKind.GPU, Confidence.LOW)),
        ("Motherboard", "VRM", (SensorKind.UNKNOWN, Confidence.LOW)),
        ("Storage", "Temperature", (SensorKind.UNKNOWN, Confidence.LOW)),
    ],
)
def test_classify_lhm_sensor(
    hardware_type: str, name: str, expected: tuple[SensorKind, Confidence] | None
) -> None:
    assert classify_lhm_sensor(hardware_type, name) == expected


def test_failures_are_not_reprobed_immediately() -> None:
    calls = {"wmi": 0, "http": 0}

    def failing_wmi(script: str) -> str:
        calls["wmi"] += 1
        raise RuntimeError("Invalid namespace")

    def failing_http(url: str) -> dict[str, Any]:
        calls["http"] += 1
        raise OSError("connection refused")

    backend = LibreHardwareMonitorBackend(wmi_runner=failing_wmi, http_fetcher=failing_http)
    assert not backend.available()
    assert backend.sensors() == []
    assert not backend.available()
    assert calls == {"wmi": 1, "http": 1}
    assert "Invalid namespace" in (backend.detail() or "")
