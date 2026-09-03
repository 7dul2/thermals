from __future__ import annotations

from pathlib import Path

import pytest

from thermals import detection
from thermals.api import cpu, gpu
from thermals.backends.linux.hwmon import HwmonBackend, classify_hwmon
from thermals.models import Confidence, SensorKind


def backend(fixtures: Path, name: str) -> HwmonBackend:
    return HwmonBackend(fixtures / "linux" / name / "hwmon")


def test_intel_desktop(fixtures: Path) -> None:
    b = backend(fixtures, "intel_desktop")
    assert b.available()
    assert b.detail() is None
    readings = {r.name: r for r in b.sensors()}
    pkg = readings["coretemp Package id 0"]
    assert pkg.value == 52.0
    assert pkg.kind is SensorKind.CPU_PACKAGE
    assert pkg.confidence is Confidence.HIGH
    assert pkg.source == "hwmon"
    core = readings["coretemp Core 1"]
    assert (core.kind, core.confidence, core.value) == (SensorKind.CPU_CORE, Confidence.HIGH, 51.0)
    acpi = readings["acpitz temp1"]
    assert (acpi.kind, acpi.confidence, acpi.value) == (
        SensorKind.THERMAL_ZONE,
        Confidence.LOW,
        27.8,
    )
    assert readings["nvme Composite"].kind is SensorKind.UNKNOWN
    assert readings["pch_cannonlake temp1"].kind is SensorKind.UNKNOWN

    detection.set_backends([b])
    assert cpu().name == "coretemp Package id 0"
    assert gpu().value is None


def test_amd_desktop(fixtures: Path) -> None:
    b = backend(fixtures, "amd_desktop")
    readings = {r.name: r for r in b.sensors()}
    assert readings["k10temp Tctl"].kind is SensorKind.CPU_CONTROL
    assert readings["k10temp Tdie"].kind is SensorKind.CPU_DIE
    assert readings["k10temp Tccd1"].kind is SensorKind.CPU_DIE
    assert readings["amdgpu edge"].kind is SensorKind.GPU
    assert readings["amdgpu edge"].confidence is Confidence.HIGH
    assert readings["amdgpu junction"].confidence is Confidence.MEDIUM
    assert readings["amdgpu mem"].kind is SensorKind.UNKNOWN

    detection.set_backends([b])
    selected = cpu()
    # Tdie (51.25) beats Tctl (61.25) even though Tctl is hotter: kind priority wins.
    assert selected.kind is SensorKind.CPU_DIE
    assert selected.value == 51.25
    assert selected.name == "k10temp Tdie"
    assert gpu().name == "amdgpu edge"


def test_legacy_device_directory(fixtures: Path) -> None:
    b = backend(fixtures, "legacy_device_dir")
    assert b.available()
    names = sorted(r.name or "" for r in b.sensors())
    assert names == ["coretemp Core 0", "coretemp Physical id 0"]
    assert b.sensors()[0].kind is SensorKind.CPU_PACKAGE


def test_arm_sbc(fixtures: Path) -> None:
    b = backend(fixtures, "arm_sbc")
    [r] = b.sensors()
    assert (r.kind, r.confidence, r.value) == (SensorKind.CPU_DIE, Confidence.MEDIUM, 45.3)


def test_broken_values_are_skipped(fixtures: Path) -> None:
    b = backend(fixtures, "broken")
    readings = b.sensors()
    assert [r.name for r in readings] == ["acpitz temp1"]


def test_empty_and_missing_roots(fixtures: Path, tmp_path: Path) -> None:
    empty = backend(fixtures, "empty")
    assert not empty.available()
    assert empty.sensors() == []
    assert "no temperature inputs" in (empty.detail() or "")
    missing = HwmonBackend(tmp_path / "nope")
    assert not missing.available()
    assert missing.sensors() == []
    assert "does not exist" in (missing.detail() or "")


@pytest.mark.parametrize(
    ("chip", "label", "kind", "confidence"),
    [
        ("coretemp", "Package id 0", SensorKind.CPU_PACKAGE, Confidence.HIGH),
        ("coretemp", "Core 7", SensorKind.CPU_CORE, Confidence.HIGH),
        ("coretemp", "weird", SensorKind.UNKNOWN, Confidence.MEDIUM),
        ("k10temp", "Tctl", SensorKind.CPU_CONTROL, Confidence.HIGH),
        ("k10temp", "Tdie", SensorKind.CPU_DIE, Confidence.HIGH),
        ("k10temp", "Tccd2", SensorKind.CPU_DIE, Confidence.HIGH),
        ("k10temp", None, SensorKind.CPU_CONTROL, Confidence.MEDIUM),
        ("zenpower", "Tdie", SensorKind.CPU_DIE, Confidence.HIGH),
        ("amdgpu", "edge", SensorKind.GPU, Confidence.HIGH),
        ("nouveau", None, SensorKind.GPU, Confidence.HIGH),
        ("i915", None, SensorKind.GPU, Confidence.HIGH),
        ("cpu_thermal", None, SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("soc_thermal", None, SensorKind.SOC, Confidence.MEDIUM),
        ("acpitz", None, SensorKind.THERMAL_ZONE, Confidence.LOW),
        ("nvme", "Composite", SensorKind.UNKNOWN, Confidence.LOW),
        ("dell_smm", "CPU", SensorKind.CPU_PACKAGE, Confidence.LOW),
        ("dell_smm", "GPU", SensorKind.GPU, Confidence.MEDIUM),
        ("thinkpad", "CPU package", SensorKind.CPU_PACKAGE, Confidence.MEDIUM),
        ("asus", "Core 0", SensorKind.CPU_CORE, Confidence.MEDIUM),
        ("something", "Tdie", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("something", "Tctl", SensorKind.CPU_CONTROL, Confidence.MEDIUM),
        ("something", None, SensorKind.UNKNOWN, Confidence.LOW),
    ],
)
def test_classify_hwmon(
    chip: str, label: str | None, kind: SensorKind, confidence: Confidence
) -> None:
    assert classify_hwmon(chip, label) == (kind, confidence)
