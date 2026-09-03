from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest

from thermals import detection
from thermals.backends.base import ThermalBackend
from thermals.models import Stability, TemperatureReading, ThermalState

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_detection() -> Iterator[None]:
    detection.reset()
    yield
    detection.reset()


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def load_json(relative: str) -> Any:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


def load_text(relative: str) -> str:
    return (FIXTURES / relative).read_text(encoding="utf-8")


def load_readings(relative: str) -> list[tuple[str, float]]:
    """Load ``[[name, value], ...]`` fixture files for the macOS reader backends."""
    return [(str(name), float(value)) for name, value in load_json(relative)["readings"]]


class FakeBackend(ThermalBackend):
    """Backend returning canned data for API and CLI tests."""

    name: ClassVar[str] = "fake"
    stability: ClassVar[Stability] = Stability.STABLE

    def __init__(
        self,
        readings: list[TemperatureReading] | None = None,
        state: ThermalState | None = None,
        available: bool = True,
        name: str = "fake",
        raise_on_sensors: bool = False,
        raise_on_available: bool = False,
    ) -> None:
        self._readings = readings or []
        self._state = state
        self._available = available
        self._raise_on_sensors = raise_on_sensors
        self._raise_on_available = raise_on_available
        self.name = name  # type: ignore[misc]

    def available(self) -> bool:
        if self._raise_on_available:
            raise RuntimeError("boom")
        return self._available

    def detail(self) -> str | None:
        return None if self._available else "fake backend disabled"

    def sensors(self) -> list[TemperatureReading]:
        if self._raise_on_sensors:
            raise RuntimeError("sensor failure")
        return list(self._readings)

    def thermal_state(self) -> ThermalState | None:
        return self._state
