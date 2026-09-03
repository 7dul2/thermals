"""``python -m thermals`` must never crash, whatever hardware the machine has."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

import thermals


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "thermals", *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize("args", [(), ("--all",), ("--debug",), ("--min-confidence", "low")])
def test_module_runs(args: tuple[str, ...]) -> None:
    result = run(*args)
    assert result.returncode == 0, result.stderr
    assert "Source" in result.stdout
    assert "Traceback" not in result.stderr


def test_json_is_valid() -> None:
    result = run("--json", "--all")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert set(data) >= {"cpu", "gpu", "thermal_state", "backend", "backends", "sensors"}
    assert data["cpu"]["temperature"] is None or isinstance(data["cpu"]["temperature"], float)


def test_public_api_types() -> None:
    value = thermals.cpu_temperature()
    assert value is None or isinstance(value, float)
    value = thermals.gpu_temperature()
    assert value is None or isinstance(value, float)
    assert isinstance(thermals.thermal_state(), thermals.ThermalState)
    assert isinstance(thermals.sensors(), list)
    assert thermals.backend() is None or isinstance(thermals.backend(), str)
    snap = thermals.snapshot()
    assert isinstance(snap, thermals.Snapshot)
    json.dumps(snap.to_dict())
