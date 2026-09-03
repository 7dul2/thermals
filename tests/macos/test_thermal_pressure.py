from __future__ import annotations

import sys

import pytest

from thermals import detection
from thermals.api import thermal_state
from thermals.backends.macos.thermal_pressure import (
    ThermalPressureBackend,
    map_thermal_state,
    read_thermal_state_code,
)
from thermals.models import ThermalState


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, ThermalState.NOMINAL),
        (1, ThermalState.FAIR),
        (2, ThermalState.SERIOUS),
        (3, ThermalState.CRITICAL),
        (4, ThermalState.UNKNOWN),
        (-1, ThermalState.UNKNOWN),
    ],
)
def test_map_thermal_state(code: int, expected: ThermalState) -> None:
    assert map_thermal_state(code) is expected


def test_backend_with_reader() -> None:
    backend = ThermalPressureBackend(reader=lambda: 2)
    assert backend.available()
    assert backend.detail() is None
    assert backend.sensors() == []
    assert backend.thermal_state() is ThermalState.SERIOUS
    detection.set_backends([backend])
    assert thermal_state() is ThermalState.SERIOUS


def test_backend_reader_failure() -> None:
    def broken() -> int:
        raise RuntimeError("objc failure")

    backend = ThermalPressureBackend(reader=broken)
    assert not backend.available()
    assert backend.detail() == "objc failure"
    assert backend.thermal_state() is None


@pytest.mark.skipif(sys.platform == "darwin", reason="checks the non-macOS path")
def test_backend_unavailable_off_macos() -> None:
    backend = ThermalPressureBackend()
    assert not backend.available()
    assert backend.detail() == "not running on macOS"


@pytest.mark.skipif(sys.platform != "darwin", reason="needs macOS Foundation")
def test_real_reader_returns_valid_code() -> None:
    code = read_thermal_state_code()
    assert code in (0, 1, 2, 3)
