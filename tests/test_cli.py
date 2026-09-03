from __future__ import annotations

import json

import pytest

from tests.conftest import FakeBackend
from thermals import cli, detection
from thermals.models import Confidence, SensorKind, TemperatureReading, ThermalState


def reading(
    value: float, kind: SensorKind, name: str, confidence: Confidence = Confidence.HIGH
) -> TemperatureReading:
    return TemperatureReading(
        value=value, kind=kind, source="fake", name=name, confidence=confidence
    )


@pytest.fixture
def rich_system() -> None:
    detection.set_backends(
        [
            FakeBackend(
                [
                    reading(52.4, SensorKind.CPU_PACKAGE, "CPU Package"),
                    reading(55.1, SensorKind.CPU_CORE, "Core 0"),
                    reading(53.0, SensorKind.CPU_CORE, "Core 1"),
                    reading(43.8, SensorKind.GPU, "GPU Core"),
                ],
                state=ThermalState.NOMINAL,
                name="fakemon",
            )
        ]
    )


def test_default_output(rich_system: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == [
        "CPU Package        52.4 °C",
        "CPU Core Max       55.1 °C",
        "GPU                43.8 °C",
        "Thermal State     Nominal",
        "Source            fakemon",
    ]


def test_all_output(rich_system: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--all"]) == 0
    out = capsys.readouterr().out
    assert "Sensors (4)" in out
    assert "Core 1" in out
    assert "cpu_core" in out
    assert "fake" in out


def test_json_output(rich_system: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["cpu"]["temperature"] == 52.4
    assert data["cpu"]["kind"] == "cpu_package"
    assert data["cpu"]["source"] == "fake"
    assert data["cpu"]["confidence"] == "high"
    assert data["thermal_state"] == "nominal"
    assert data["backend"] == "fakemon"
    assert "sensors" not in data

    assert cli.main(["--json", "--all"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["sensors"]) == 4


def test_unavailable_output(capsys: pytest.CaptureFixture[str]) -> None:
    detection.set_backends(
        [
            FakeBackend(
                [reading(27.8, SensorKind.THERMAL_ZONE, "TZ00", Confidence.LOW)], name="acpi-ish"
            )
        ]
    )
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "CPU Temperature   unavailable" in out
    assert "Only low-confidence CPU sensors" in out
    assert "GPU               unavailable" in out
    assert "Thermal State" not in out
    assert "Source            acpi-ish" in out

    assert cli.main(["--min-confidence", "low"]) == 0
    out = capsys.readouterr().out
    assert "CPU (thermal zone) 27.8 °C" in out


def test_nothing_at_all(capsys: pytest.CaptureFixture[str]) -> None:
    detection.set_backends([])
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "CPU Temperature   unavailable" in out
    assert "No supported temperature sensor available" in out
    assert "Source            none" in out
    assert cli.main(["--all"]) == 0
    assert "Sensors           none" in capsys.readouterr().out


def test_debug_report(rich_system: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--debug"]) == 0
    captured = capsys.readouterr()
    assert "[debug] backend fakemon: available [stable]" in captured.err
    assert "CPU Package" in captured.out


def test_watch_runs_until_interrupted(
    rich_system: None, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = {"n": 0}

    def fake_sleep(seconds: float) -> None:
        ticks["n"] += 1
        if ticks["n"] >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr("thermals.cli.time.sleep", fake_sleep)
    assert cli.main(["--watch", "0.01", "--json"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2
    assert all(json.loads(line)["cpu"]["temperature"] == 52.4 for line in lines)


def test_watch_default_interval(rich_system: None, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[float] = []

    def fake_sleep(seconds: float) -> None:
        seen.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr("thermals.cli.time.sleep", fake_sleep)
    assert cli.main(["--watch"]) == 0
    assert seen and 0.0 <= seen[0] <= 1.0


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.startswith("thermals ")


def test_unexpected_error_is_reported_not_raised(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(min_confidence: Confidence) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr("thermals.cli.api.snapshot", explode)
    assert cli.main([]) == 1
    assert "kaboom" in capsys.readouterr().err
    with pytest.raises(RuntimeError):
        cli.main(["--debug"])
