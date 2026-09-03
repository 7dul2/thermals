"""Real hardware checks. Skipped by default; run with ``pytest -m hardware``."""

from __future__ import annotations

import platform

import pytest

import thermals
from thermals.models import Confidence, SensorKind, ThermalState

pytestmark = pytest.mark.hardware


def test_a_backend_is_available() -> None:
    assert thermals.backend() is not None, thermals.list_backends()


def test_sensors_have_values() -> None:
    readings = thermals.sensors()
    assert readings, "no sensors reported"
    for reading in readings:
        assert reading.value is not None
        assert -40.0 <= reading.value <= 150.0
        assert reading.kind in SensorKind
        assert reading.confidence in Confidence


def test_cpu_temperature_is_available() -> None:
    reading = thermals.cpu()
    assert reading.value is not None, reading.reason
    assert 0.0 < reading.value < 130.0
    assert reading.kind is not SensorKind.UNKNOWN


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_macos_thermal_state() -> None:
    assert thermals.thermal_state() is not ThermalState.UNKNOWN


@pytest.mark.skipif(
    platform.system() != "Darwin" or platform.machine() != "arm64", reason="Apple Silicon only"
)
def test_apple_silicon_backends() -> None:
    names = {b.name for b in thermals.list_backends() if b.available}
    assert {"thermal_pressure", "apple_smc", "apple_silicon"} <= names
    assert thermals.gpu_temperature() is not None
