from __future__ import annotations

import thermals
from tests.conftest import FakeBackend
from thermals import api, detection
from thermals.models import Confidence, SensorKind, TemperatureReading, ThermalState


def reading(
    value: float | None,
    kind: SensorKind,
    confidence: Confidence = Confidence.HIGH,
    source: str = "fake",
    name: str | None = None,
) -> TemperatureReading:
    return TemperatureReading(
        value=value, kind=kind, source=source, name=name, confidence=confidence
    )


def test_cpu_prefers_package_over_cores() -> None:
    detection.set_backends(
        [
            FakeBackend(
                [
                    reading(55.0, SensorKind.CPU_CORE, name="Core 0"),
                    reading(52.0, SensorKind.CPU_PACKAGE, name="Package id 0"),
                    reading(58.0, SensorKind.CPU_CORE, name="Core 1"),
                ]
            )
        ]
    )
    result = thermals.cpu()
    assert result.kind is SensorKind.CPU_PACKAGE
    assert result.value == 52.0
    assert thermals.cpu_temperature() == 52.0


def test_cpu_uses_hottest_core_when_no_package() -> None:
    detection.set_backends(
        [
            FakeBackend(
                [
                    reading(55.0, SensorKind.CPU_CORE, name="Core 0"),
                    reading(58.0, SensorKind.CPU_CORE, name="Core 1"),
                    reading(61.0, SensorKind.CPU_CONTROL, name="Tctl"),
                ]
            )
        ]
    )
    result = thermals.cpu()
    assert result.kind is SensorKind.CPU_CORE
    assert result.value == 58.0
    assert result.name == "Core 1"


def test_cpu_die_beats_control() -> None:
    detection.set_backends(
        [
            FakeBackend(
                [
                    reading(61.0, SensorKind.CPU_CONTROL, name="Tctl"),
                    reading(51.0, SensorKind.CPU_DIE, name="Tdie"),
                ]
            )
        ]
    )
    assert thermals.cpu().kind is SensorKind.CPU_DIE


def test_low_confidence_thermal_zone_is_rejected_by_default() -> None:
    detection.set_backends(
        [FakeBackend([reading(27.8, SensorKind.THERMAL_ZONE, Confidence.LOW, source="acpi")])]
    )
    result = thermals.cpu()
    assert result.value is None
    assert thermals.cpu_temperature() is None
    assert result.reason is not None
    assert "thermal_zone/low from acpi" in result.reason
    assert "min_confidence=Confidence.LOW" in result.reason

    accepted = thermals.cpu(min_confidence=Confidence.LOW)
    assert accepted.value == 27.8
    assert accepted.kind is SensorKind.THERMAL_ZONE
    assert thermals.cpu_temperature(min_confidence=Confidence.LOW) == 27.8


def test_soc_used_before_thermal_zone() -> None:
    detection.set_backends(
        [
            FakeBackend(
                [
                    reading(40.0, SensorKind.SOC, Confidence.MEDIUM),
                    reading(30.0, SensorKind.THERMAL_ZONE, Confidence.MEDIUM),
                ]
            )
        ]
    )
    assert thermals.cpu().kind is SensorKind.SOC


def test_no_sensors_reason() -> None:
    detection.set_backends([FakeBackend([])])
    result = thermals.cpu()
    assert result.value is None
    assert result.reason == "No supported temperature sensor available"


def test_only_other_kinds_reason() -> None:
    detection.set_backends([FakeBackend([reading(40.0, SensorKind.GPU)])])
    result = thermals.cpu()
    assert result.value is None
    assert result.reason is not None
    assert result.reason.startswith("No CPU temperature sensor found")
    assert thermals.gpu().value == 40.0
    assert thermals.gpu_temperature() == 40.0


def test_gpu_unavailable() -> None:
    detection.set_backends([FakeBackend([reading(40.0, SensorKind.CPU_PACKAGE)])])
    assert thermals.gpu_temperature() is None


def test_readings_without_value_are_ignored() -> None:
    detection.set_backends([FakeBackend([reading(None, SensorKind.CPU_PACKAGE)])])
    result = thermals.cpu()
    assert result.value is None
    assert result.reason == "No supported temperature sensor available"


def test_thermal_state_from_first_backend_that_knows() -> None:
    detection.set_backends(
        [
            FakeBackend([], state=None, name="a"),
            FakeBackend([], state=ThermalState.FAIR, name="b"),
            FakeBackend([], state=ThermalState.CRITICAL, name="c"),
        ]
    )
    assert thermals.thermal_state() is ThermalState.FAIR


def test_thermal_state_unknown_without_backends() -> None:
    detection.set_backends([])
    assert thermals.thermal_state() is ThermalState.UNKNOWN
    assert thermals.backend() is None
    assert thermals.sensors() == []


def test_failing_backends_are_skipped() -> None:
    detection.set_backends(
        [
            FakeBackend([], raise_on_available=True, name="broken-avail"),
            FakeBackend([], raise_on_sensors=True, name="broken-sensors"),
            FakeBackend([reading(50.0, SensorKind.CPU_PACKAGE)], name="good"),
        ]
    )
    assert thermals.cpu_temperature() == 50.0
    assert thermals.backend() == "broken-sensors"
    names = [b.name for b in thermals.list_backends()]
    assert names == ["broken-avail", "broken-sensors", "good"]


def test_snapshot_reads_everything_once() -> None:
    backend = FakeBackend(
        [reading(50.0, SensorKind.CPU_PACKAGE), reading(45.0, SensorKind.GPU)],
        state=ThermalState.NOMINAL,
        name="one",
    )
    detection.set_backends([backend, FakeBackend([], available=False, name="off")])
    snap = thermals.snapshot()
    assert snap.cpu.value == 50.0
    assert snap.gpu.value == 45.0
    assert snap.thermal_state is ThermalState.NOMINAL
    assert snap.backend == "one"
    assert [b.available for b in snap.backends] == [True, False]
    assert snap.backends[1].detail == "fake backend disabled"
    assert len(snap.sensors) == 2
    assert snap.timestamp > 0


def test_select_reading_source_fallback() -> None:
    result = api.select_reading([], api.CPU_KIND_PRIORITY, Confidence.MEDIUM, "CPU", "hwmon")
    assert result.source == "hwmon"
    result = api.select_reading([], api.CPU_KIND_PRIORITY, Confidence.MEDIUM, "CPU")
    assert result.source == "none"
