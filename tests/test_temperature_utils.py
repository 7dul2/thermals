from __future__ import annotations

import pytest

from thermals.utils.temperature import (
    celsius_to_fahrenheit,
    decikelvin_to_celsius,
    is_plausible,
    millidegrees_to_celsius,
    parse_float,
)


def test_conversions() -> None:
    assert millidegrees_to_celsius("52000") == 52.0
    assert millidegrees_to_celsius(52125) == 52.125
    assert decikelvin_to_celsius(3032) == pytest.approx(30.05)
    assert celsius_to_fahrenheit(100.0) == 212.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (25.0, True),
        (-40.0, True),
        (150.0, True),
        (-41.0, False),
        (151.0, False),
        (float("nan"), False),
    ],
)
def test_is_plausible(value: float, expected: bool) -> None:
    assert is_plausible(value) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("45.0 °C", 45.0),
        ("45,5 °C", 45.5),
        ("  -3.25C", -3.25),
        ("+7", 7.0),
        ("", None),
        ("abc", None),
        (None, None),
        ("-", None),
    ],
)
def test_parse_float(text: str | None, expected: float | None) -> None:
    assert parse_float(text) == expected
