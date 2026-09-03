from __future__ import annotations

import pytest

from tests.conftest import FakeBackend
from thermals import detection


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", ["thermal_pressure", "apple_smc", "apple_silicon", "powermetrics"]),
        ("Darwin", "x86_64", ["thermal_pressure", "apple_smc", "powermetrics"]),
        ("Windows", "AMD64", ["librehardwaremonitor", "acpi"]),
        ("Linux", "x86_64", ["hwmon", "thermal_zone"]),
        ("Linux", "aarch64", ["hwmon", "thermal_zone"]),
        ("FreeBSD", "amd64", []),
    ],
)
def test_candidate_backends(system: str, machine: str, expected: list[str]) -> None:
    names = [b.name for b in detection.candidate_backends(system, machine)]
    assert names == expected


def test_backends_are_cached_and_resettable() -> None:
    first = detection.backends()
    second = detection.backends()
    assert [id(b) for b in first] == [id(b) for b in second]
    detection.reset()
    third = detection.backends()
    assert [b.name for b in third] == [b.name for b in first]


def test_set_backends_override() -> None:
    fake = FakeBackend([], name="custom")
    detection.set_backends([fake])
    assert detection.backends() == [fake]
    assert detection.available_backends() == [fake]
    detection.set_backends(None)
    assert fake not in detection.backends()


def test_debug_report_lists_backends() -> None:
    detection.set_backends(
        [FakeBackend([], name="on"), FakeBackend([], available=False, name="off")]
    )
    report = detection.debug_report()
    assert report[0].startswith("platform:")
    assert "backend on: available [stable]" in report[1]
    assert "backend off: unavailable [stable] - fake backend disabled" in report[2]
