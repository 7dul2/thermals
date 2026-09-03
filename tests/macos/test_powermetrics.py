from __future__ import annotations

from tests.conftest import load_text
from thermals import detection
from thermals.api import cpu, thermal_state
from thermals.backends.macos.powermetrics import PowermetricsBackend, parse_powermetrics
from thermals.models import Confidence, SensorKind, ThermalState


def test_parse_intel() -> None:
    readings, state = parse_powermetrics(load_text("macos/powermetrics_intel.txt"))
    assert state is None
    assert [(r.name, r.value, r.kind) for r in readings] == [
        ("CPU die temperature", 52.34, SensorKind.CPU_DIE),
        ("GPU die temperature", 45.0, SensorKind.GPU),
    ]
    assert readings[0].confidence is Confidence.MEDIUM
    assert readings[0].source == "powermetrics"


def test_parse_apple_silicon() -> None:
    readings, state = parse_powermetrics(load_text("macos/powermetrics_apple_silicon.txt"))
    assert readings == []
    assert state is ThermalState.NOMINAL
    _, heavy = parse_powermetrics(load_text("macos/powermetrics_heavy.txt"))
    assert heavy is ThermalState.SERIOUS
    _, weird = parse_powermetrics("Current pressure level: Purple\n")
    assert weird is ThermalState.UNKNOWN


def test_backend_with_runner() -> None:
    backend = PowermetricsBackend(runner=lambda: load_text("macos/powermetrics_intel.txt"))
    assert backend.available()
    assert backend.detail() is None
    assert backend.thermal_state() is None
    detection.set_backends([backend])
    assert cpu().value == 52.34

    pressure = PowermetricsBackend(runner=lambda: load_text("macos/powermetrics_heavy.txt"))
    assert pressure.available()
    assert pressure.sensors() == []
    detection.set_backends([pressure])
    assert thermal_state() is ThermalState.SERIOUS


def test_backend_failure() -> None:
    def broken() -> str:
        raise RuntimeError("powermetrics must be invoked as the superuser")

    backend = PowermetricsBackend(runner=broken)
    assert not backend.available()
    assert "superuser" in (backend.detail() or "")
    assert backend.sensors() == []
    assert backend.thermal_state() is None


def test_backend_requires_root_or_macos() -> None:
    backend = PowermetricsBackend()
    # Never root in the test suite; off macOS it is simply the wrong platform.
    assert not backend.available()
    assert backend.detail() in {"powermetrics requires root", "not running on macOS"}
