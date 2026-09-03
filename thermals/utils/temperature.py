"""Unit conversion and plausibility helpers."""

from __future__ import annotations

MIN_PLAUSIBLE_CELSIUS = -40.0
MAX_PLAUSIBLE_CELSIUS = 150.0


def is_plausible(value: float) -> bool:
    """Return ``True`` if ``value`` looks like a real component temperature.

    Drivers sometimes report ``0``, ``-273.15`` or huge values for
    unpopulated sensors. Those are dropped instead of being presented as data.
    """
    if value != value:  # NaN
        return False
    return MIN_PLAUSIBLE_CELSIUS <= value <= MAX_PLAUSIBLE_CELSIUS


def millidegrees_to_celsius(raw: int | float | str) -> float:
    """Convert Linux sysfs millidegree values (``52000``) to Celsius."""
    return float(raw) / 1000.0


def decikelvin_to_celsius(raw: int | float | str) -> float:
    """Convert ACPI tenths-of-Kelvin values (``3032``) to Celsius."""
    return float(raw) / 10.0 - 273.15


def celsius_to_fahrenheit(value: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return value * 9.0 / 5.0 + 32.0


def parse_float(text: str | None) -> float | None:
    """Parse the leading number of ``text`` (``"45.0 °C"`` or ``"45,0"``)."""
    if text is None:
        return None
    cleaned = text.strip().replace(",", ".")
    number = ""
    for ch in cleaned:
        if ch.isdigit() or (ch in "+-." and (not number or ch == ".")):
            number += ch
        else:
            break
    if number in ("", "+", "-", "."):
        return None
    try:
        return float(number)
    except ValueError:
        return None
