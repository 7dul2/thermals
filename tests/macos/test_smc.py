from __future__ import annotations

import struct

import pytest

from tests.conftest import load_readings
from thermals import detection
from thermals.api import cpu, gpu
from thermals.backends.macos.smc import (
    AppleSMCBackend,
    classify_smc_key,
    decode_smc_value,
    is_temperature_type,
)
from thermals.models import Confidence, SensorKind


def test_decode_types() -> None:
    assert decode_smc_value("flt ", struct.pack("<f", 36.5)) == pytest.approx(36.5)
    assert decode_smc_value("ioft", struct.pack("<Q", 29 * 65536)) == 29.0
    assert decode_smc_value("sp78", struct.pack(">h", 0x3480)) == pytest.approx(52.5)
    assert decode_smc_value("sp78", struct.pack(">h", -256)) == -1.0
    assert decode_smc_value("fpe2", struct.pack(">H", 4 * 100)) == 100.0
    assert decode_smc_value("ui8 ", b"\x2a") == 42.0
    assert decode_smc_value("si8 ", b"\xff") == -1.0
    assert decode_smc_value("ui16", b"\x01\x00") == 256.0
    assert decode_smc_value("si16", b"\xff\xfe") == -2.0
    assert decode_smc_value("ui32", b"\x00\x00\x01\x00") == 256.0
    assert decode_smc_value("flt ", b"\x00") is None  # wrong length
    assert decode_smc_value("ch8*", b"abcd") is None  # unsupported
    assert decode_smc_value("spzz", b"\x00\x00") is None  # invalid hex digit


def test_is_temperature_type() -> None:
    assert is_temperature_type("flt ")
    assert is_temperature_type("sp78")
    assert is_temperature_type("ioft")
    assert not is_temperature_type("ui8 ")
    assert not is_temperature_type("ch8*")


@pytest.mark.parametrize(
    ("key", "kind", "confidence"),
    [
        ("Tp00", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("Te08", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("Tf04", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("Tf49", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("Tf14", SensorKind.GPU, Confidence.MEDIUM),
        ("Tf2A", SensorKind.GPU, Confidence.MEDIUM),
        ("Tf9Z", SensorKind.UNKNOWN, Confidence.LOW),
        ("Tg0G", SensorKind.GPU, Confidence.MEDIUM),
        ("TPD0", SensorKind.SOC, Confidence.MEDIUM),
        ("TRD3", SensorKind.SOC, Confidence.MEDIUM),
        ("TB0T", SensorKind.UNKNOWN, Confidence.LOW),
        ("TH0T", SensorKind.UNKNOWN, Confidence.LOW),
        ("TW0P", SensorKind.UNKNOWN, Confidence.LOW),
        ("TVD0", SensorKind.UNKNOWN, Confidence.LOW),
    ],
)
def test_classify_apple_silicon(key: str, kind: SensorKind, confidence: Confidence) -> None:
    assert classify_smc_key(key, apple_silicon=True)[:2] == (kind, confidence)


@pytest.mark.parametrize(
    ("key", "kind", "confidence"),
    [
        ("TC0D", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("TC0E", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("TC0F", SensorKind.CPU_DIE, Confidence.MEDIUM),
        ("TC0C", SensorKind.CPU_CORE, Confidence.MEDIUM),
        ("TC3C", SensorKind.CPU_CORE, Confidence.MEDIUM),
        ("TCXC", SensorKind.CPU_PACKAGE, Confidence.MEDIUM),
        ("TC0P", SensorKind.CPU_PACKAGE, Confidence.LOW),
        ("TCGC", SensorKind.GPU, Confidence.MEDIUM),
        ("TG0D", SensorKind.GPU, Confidence.MEDIUM),
        ("TG0P", SensorKind.GPU, Confidence.LOW),
        ("TA0P", SensorKind.UNKNOWN, Confidence.LOW),
        ("TB0T", SensorKind.UNKNOWN, Confidence.LOW),
        ("TH0P", SensorKind.UNKNOWN, Confidence.LOW),
        ("Tm0P", SensorKind.UNKNOWN, Confidence.LOW),
    ],
)
def test_classify_intel(key: str, kind: SensorKind, confidence: Confidence) -> None:
    assert classify_smc_key(key, apple_silicon=False)[:2] == (kind, confidence)


def test_backend_m5_fixture() -> None:
    readings = load_readings("macos/smc_m5.json")
    backend = AppleSMCBackend(reader=lambda: readings, apple_silicon=True)
    assert backend.available()
    assert backend.detail() is None
    sensors = backend.sensors()
    assert all(r.source == "applesmc" for r in sensors)
    assert all(r.value is not None and r.value > 0 for r in sensors)
    names = {r.name for r in sensors}
    assert "CPU performance core (Tp00)" in names
    assert "GPU (Tg0G)" in names
    assert not any("TPDD" in (n or "") for n in names)  # 0.0 valued keys dropped

    detection.set_backends([backend])
    selected = cpu()
    assert selected.kind is SensorKind.CPU_DIE
    assert selected.confidence is Confidence.MEDIUM
    assert selected.name is not None and selected.name.startswith("CPU ")
    assert gpu().kind is SensorKind.GPU


def test_backend_intel_fixture() -> None:
    readings = load_readings("macos/smc_intel_synthetic.json")
    backend = AppleSMCBackend(reader=lambda: readings, apple_silicon=False)
    detection.set_backends([backend])
    selected = cpu()
    assert selected.name == "CPU package (PECI) (TCXC)"
    assert selected.value == 55.0
    assert gpu().name == "GPU die 0 (TG0D)"


def test_backend_failure_paths() -> None:
    def broken() -> list[tuple[str, float]]:
        raise RuntimeError("IOServiceOpen failed")

    backend = AppleSMCBackend(reader=broken, apple_silicon=True)
    assert not backend.available()
    assert backend.detail() == "IOServiceOpen failed"

    empty = AppleSMCBackend(reader=list, apple_silicon=True)
    assert not empty.available()
    assert empty.detail() == "SMC exposes no temperature keys"
