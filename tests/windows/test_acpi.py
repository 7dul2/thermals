from __future__ import annotations

import pytest

from tests.conftest import load_text
from thermals import detection
from thermals.api import cpu
from thermals.backends.windows.acpi import (
    ACPI_SCRIPT,
    ACPIThermalZoneBackend,
    parse_acpi_payload,
)
from thermals.models import Confidence, SensorKind


def test_parse_list_payload() -> None:
    readings = parse_acpi_payload(load_text("windows/acpi_thermal_zone.json"))
    # TZ01 reports 2732 (0 C) and TZ02 has no value: both dropped.
    assert len(readings) == 1
    [zone] = readings
    assert zone.name == "ACPI\\ThermalZone\\TZ00_0"
    assert zone.value == pytest.approx(30.05)
    assert zone.kind is SensorKind.THERMAL_ZONE
    assert zone.confidence is Confidence.LOW
    assert zone.source == "acpi"


def test_parse_single_object_payload() -> None:
    [zone] = parse_acpi_payload(load_text("windows/acpi_thermal_zone_single.json"))
    assert zone.value == pytest.approx(45.05)


def test_parse_empty() -> None:
    assert parse_acpi_payload("") == []


def test_backend_never_claims_cpu_by_default() -> None:
    def runner(script: str) -> str:
        assert script == ACPI_SCRIPT
        return load_text("windows/acpi_thermal_zone.json")

    backend = ACPIThermalZoneBackend(runner=runner)
    assert backend.available()
    assert backend.detail() is None
    detection.set_backends([backend])
    result = cpu()
    assert result.value is None
    assert "thermal_zone/low from acpi" in (result.reason or "")
    assert cpu(min_confidence=Confidence.LOW).value == pytest.approx(30.05)


def test_backend_failure_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(script: str) -> str:
        raise RuntimeError("Access denied")

    backend = ACPIThermalZoneBackend(runner=denied)
    assert not backend.available()
    assert backend.detail() == "Access denied"
    assert backend.sensors() == []

    empty = ACPIThermalZoneBackend(runner=lambda script: "[]")
    assert not empty.available()
    assert empty.detail() == "no ACPI thermal zones reported"

    monkeypatch.setattr("thermals.backends.windows.acpi.sys.platform", "darwin")
    off_platform = ACPIThermalZoneBackend()
    assert not off_platform.available()
    assert off_platform.detail() == "not running on Windows"
