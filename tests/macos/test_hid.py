from __future__ import annotations

import pytest

from tests.conftest import load_readings
from thermals import detection
from thermals.api import cpu, gpu
from thermals.backends.macos.apple_silicon import AppleSiliconHIDBackend, classify_hid_sensor
from thermals.models import Confidence, SensorKind


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("pACC MTR Temp Sensor0", (SensorKind.CPU_DIE, Confidence.MEDIUM)),
        ("eACC MTR Temp Sensor3", (SensorKind.CPU_DIE, Confidence.MEDIUM)),
        ("GPU MTR Temp Sensor1", (SensorKind.GPU, Confidence.MEDIUM)),
        ("PMGR SOC Die Temp Sensor0", (SensorKind.SOC, Confidence.MEDIUM)),
        ("PMU tdie1", (SensorKind.SOC, Confidence.MEDIUM)),
        ("PMU2 tdie10", (SensorKind.SOC, Confidence.MEDIUM)),
        ("PMU tdev4", (SensorKind.UNKNOWN, Confidence.LOW)),
        ("ANE MTR Temp Sensor0", (SensorKind.UNKNOWN, Confidence.LOW)),
        ("NAND CH0 temp", (SensorKind.UNKNOWN, Confidence.LOW)),
        ("gas gauge battery", (SensorKind.UNKNOWN, Confidence.LOW)),
        ("mystery", (SensorKind.UNKNOWN, Confidence.LOW)),
    ],
)
def test_classify(name: str, expected: tuple[SensorKind, Confidence]) -> None:
    result = classify_hid_sensor(name)
    assert result is not None
    assert result[:2] == expected


def test_calibration_entries_are_not_sensors() -> None:
    assert classify_hid_sensor("PMU tcal") is None
    assert classify_hid_sensor("PMU2 tcal") is None


def test_m5_fixture() -> None:
    readings = load_readings("macos/hid_m5.json")
    backend = AppleSiliconHIDBackend(reader=lambda: readings)
    assert backend.available()
    sensors = backend.sensors()
    names = [r.name or "" for r in sensors]
    assert any(n.startswith("SoC die (PMU) (PMU tdie") for n in names)
    assert not any("tcal" in n for n in names)
    assert not any("tdev1)" in n for n in names)  # negative bogus value dropped
    assert all(r.source == "iohid" for r in sensors)

    detection.set_backends([backend])
    selected = cpu()
    # M5 exposes no CPU-attributable HID sensor, so the SoC die is the honest answer.
    assert selected.kind is SensorKind.SOC
    assert gpu().value is None


def test_m2_style_names() -> None:
    readings = load_readings("macos/hid_m2_synthetic.json")
    backend = AppleSiliconHIDBackend(reader=lambda: readings)
    detection.set_backends([backend])
    selected = cpu()
    assert selected.kind is SensorKind.CPU_DIE
    assert selected.value == 49.5
    assert selected.name == "CPU performance cluster (pACC MTR Temp Sensor1)"
    assert gpu().value == 40.1


def test_failure_paths() -> None:
    def broken() -> list[tuple[str, float]]:
        raise RuntimeError("IOHIDEventSystemClientCreate returned NULL")

    backend = AppleSiliconHIDBackend(reader=broken)
    assert not backend.available()
    assert "IOHIDEventSystemClientCreate" in (backend.detail() or "")

    empty = AppleSiliconHIDBackend(reader=list)
    assert not empty.available()
    assert empty.detail() == "no IOHID temperature sensors found"
