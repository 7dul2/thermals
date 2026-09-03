from __future__ import annotations

from pathlib import Path

import pytest

from thermals import detection
from thermals.api import cpu
from thermals.backends.linux.thermal_zone import ThermalZoneBackend, classify_thermal_zone
from thermals.models import Confidence, SensorKind


def backend(fixtures: Path, name: str) -> ThermalZoneBackend:
    return ThermalZoneBackend(fixtures / "linux" / name / "thermal")


def test_intel_zones(fixtures: Path) -> None:
    b = backend(fixtures, "intel_desktop")
    assert b.available()
    readings = b.sensors()
    assert [r.name for r in readings] == [
        "acpitz (thermal_zone0)",
        "x86_pkg_temp (thermal_zone1)",
        "TCPU (thermal_zone2)",
    ]
    assert readings[0].kind is SensorKind.THERMAL_ZONE
    assert readings[0].confidence is Confidence.LOW
    assert readings[1].kind is SensorKind.CPU_PACKAGE
    assert readings[1].confidence is Confidence.MEDIUM
    assert readings[1].value == 52.0
    assert readings[2].kind is SensorKind.THERMAL_ZONE

    detection.set_backends([b])
    assert cpu().name == "x86_pkg_temp (thermal_zone1)"


def test_arm_zones(fixtures: Path) -> None:
    b = backend(fixtures, "arm_sbc")
    kinds = [r.kind for r in b.sensors()]
    assert kinds == [SensorKind.CPU_DIE, SensorKind.GPU, SensorKind.SOC]


def test_empty_and_missing(fixtures: Path, tmp_path: Path) -> None:
    empty = backend(fixtures, "empty")
    assert not empty.available()
    assert "no thermal zones" in (empty.detail() or "")
    missing = ThermalZoneBackend(tmp_path / "none")
    assert not missing.available()
    assert missing.sensors() == []


def test_unreadable_temp_is_skipped(tmp_path: Path) -> None:
    zone = tmp_path / "thermal_zone0"
    zone.mkdir()
    (zone / "type").write_text("acpitz\n")
    # no temp file at all
    b = ThermalZoneBackend(tmp_path)
    assert not b.available()
    (zone / "temp").write_text("not-a-number\n")
    assert b.available()
    assert b.sensors() == []


@pytest.mark.parametrize(
    ("zone_type", "kind", "confidence"),
    [
        ("x86_pkg_temp", SensorKind.CPU_PACKAGE, Confidence.MEDIUM),
        ("acpitz", SensorKind.THERMAL_ZONE, Confidence.LOW),
        ("cpu-thermal", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("cpu_thermal", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("cpu-big-thermal", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("soc-thermal", SensorKind.SOC, Confidence.MEDIUM),
        ("gpu-thermal", SensorKind.GPU, Confidence.MEDIUM),
        ("TCPU", SensorKind.THERMAL_ZONE, Confidence.LOW),
        ("iwlwifi_1", SensorKind.THERMAL_ZONE, Confidence.LOW),
    ],
)
def test_classify_thermal_zone(zone_type: str, kind: SensorKind, confidence: Confidence) -> None:
    assert classify_thermal_zone(zone_type) == (kind, confidence)
