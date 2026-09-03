from __future__ import annotations

from thermals.models import (
    BackendInfo,
    Confidence,
    SensorKind,
    Snapshot,
    Stability,
    TemperatureReading,
    ThermalState,
)


def test_confidence_ordering() -> None:
    assert Confidence.HIGH.rank > Confidence.MEDIUM.rank > Confidence.LOW.rank
    assert Confidence.HIGH.at_least(Confidence.MEDIUM)
    assert Confidence.MEDIUM.at_least(Confidence.MEDIUM)
    assert not Confidence.LOW.at_least(Confidence.MEDIUM)


def test_confidence_is_string_enum() -> None:
    assert Confidence("high") is Confidence.HIGH
    assert Confidence.HIGH.value == "high"


def test_thermal_state_levels() -> None:
    assert ThermalState.NOMINAL.level == 0
    assert ThermalState.CRITICAL.level == 3
    assert ThermalState.UNKNOWN.level == -1
    assert ThermalState.FAIR.level < ThermalState.SERIOUS.level


def test_reading_properties_and_dict() -> None:
    reading = TemperatureReading(
        value=50.0,
        kind=SensorKind.CPU_PACKAGE,
        source="hwmon",
        name="coretemp Package id 0",
        confidence=Confidence.HIGH,
    )
    assert reading.unit == "C"
    assert reading.available
    assert reading.fahrenheit == 122.0
    assert reading.to_dict() == {
        "temperature": 50.0,
        "unit": "C",
        "kind": "cpu_package",
        "source": "hwmon",
        "name": "coretemp Package id 0",
        "confidence": "high",
        "reason": None,
    }


def test_unavailable_reading() -> None:
    reading = TemperatureReading(value=None, kind=SensorKind.UNKNOWN, source="none", reason="nope")
    assert not reading.available
    assert reading.fahrenheit is None
    assert reading.to_dict()["reason"] == "nope"


def test_snapshot_backend_and_dict() -> None:
    cpu = TemperatureReading(value=40.0, kind=SensorKind.CPU_DIE, source="x")
    gpu = TemperatureReading(value=None, kind=SensorKind.UNKNOWN, source="none", reason="no gpu")
    snap = Snapshot(
        cpu=cpu,
        gpu=gpu,
        thermal_state=ThermalState.NOMINAL,
        sensors=(cpu,),
        backends=(
            BackendInfo("a", False, Stability.STABLE, "off"),
            BackendInfo("b", True, Stability.EXPERIMENTAL),
        ),
        timestamp=1.0,
    )
    assert snap.backend == "b"
    data = snap.to_dict()
    assert data["backend"] == "b"
    assert data["thermal_state"] == "nominal"
    assert data["cpu"]["temperature"] == 40.0
    assert data["gpu"]["reason"] == "no gpu"
    assert data["backends"][1] == {
        "name": "b",
        "available": True,
        "stability": "experimental",
        "detail": None,
    }
    assert len(data["sensors"]) == 1


def test_snapshot_without_backends() -> None:
    reading = TemperatureReading(value=None, kind=SensorKind.UNKNOWN, source="none")
    snap = Snapshot(reading, reading, ThermalState.UNKNOWN, (), (), 0.0)
    assert snap.backend is None
