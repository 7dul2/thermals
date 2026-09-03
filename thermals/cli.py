"""Command line interface: ``thermals``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Sequence

from thermals import __version__, api, detection
from thermals.models import Confidence, SensorKind, Snapshot, TemperatureReading, ThermalState

_LABEL_WIDTH = 18

_CPU_LABELS: dict[SensorKind, str] = {
    SensorKind.CPU_PACKAGE: "CPU Package",
    SensorKind.CPU_DIE: "CPU Die",
    SensorKind.CPU_CORE: "CPU Core Max",
    SensorKind.CPU_CONTROL: "CPU Tctl",
    SensorKind.SOC: "CPU (SoC die)",
    SensorKind.THERMAL_ZONE: "CPU (thermal zone)",
    SensorKind.UNKNOWN: "CPU Temperature",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thermals",
        description="Read CPU, GPU and SoC temperatures and the system thermal state.",
    )
    parser.add_argument(
        "--all", action="store_true", help="list every sensor, not just the summary"
    )
    parser.add_argument(
        "--watch",
        nargs="?",
        const=1.0,
        type=float,
        metavar="SECONDS",
        help="refresh continuously (default interval: 1 second)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument(
        "--min-confidence",
        choices=[c.value for c in Confidence],
        default=Confidence.MEDIUM.value,
        help="lowest confidence accepted for the CPU/GPU summary (default: medium)",
    )
    parser.add_argument("--debug", action="store_true", help="show backend probing and tracebacks")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _fmt_value(reading: TemperatureReading) -> str:
    if reading.value is None:
        return "unavailable"
    return f"{reading.value:5.1f} °C"


def _line(label: str, value: str) -> str:
    return f"{label:<{_LABEL_WIDTH}}{value}"


def format_summary(snap: Snapshot, min_confidence: Confidence) -> str:
    """Render the default human readable summary."""
    lines: list[str] = []
    cpu = snap.cpu
    lines.append(_line(_CPU_LABELS.get(cpu.kind, "CPU Temperature"), _fmt_value(cpu)))
    if cpu.value is None and cpu.reason:
        lines.append(f"{'':<{_LABEL_WIDTH}}{cpu.reason}")
    if cpu.kind is not SensorKind.CPU_CORE:
        cores = [
            r
            for r in snap.sensors
            if r.kind is SensorKind.CPU_CORE
            and r.value is not None
            and r.confidence.at_least(min_confidence)
        ]
        if cores:
            hottest = max(cores, key=lambda r: r.value or 0.0)
            lines.append(_line("CPU Core Max", _fmt_value(hottest)))
    gpu = snap.gpu
    if gpu.value is not None or snap.sensors:
        lines.append(_line("GPU", _fmt_value(gpu)))
    if snap.thermal_state is not ThermalState.UNKNOWN:
        lines.append(_line("Thermal State", snap.thermal_state.value.capitalize()))
    active = [b.name for b in snap.backends if b.available]
    lines.append(_line("Source", ", ".join(active) if active else "none"))
    return "\n".join(lines)


def format_sensors(readings: Sequence[TemperatureReading]) -> str:
    """Render the ``--all`` sensor table."""
    if not readings:
        return "Sensors           none"
    rows = [
        (
            r.name or "?",
            _fmt_value(r),
            r.kind.value,
            r.confidence.value,
            r.source,
        )
        for r in readings
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(5)]
    header = ("Sensor", "Value", "Kind", "Confidence", "Source")
    widths = [max(w, len(h)) for w, h in zip(widths, header, strict=True)]
    out = [f"Sensors ({len(rows)})"]
    out.append("  " + "  ".join(h.ljust(w) for h, w in zip(header, widths, strict=True)))
    for row in rows:
        out.append("  " + "  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)))
    return "\n".join(out)


def render(
    snap: Snapshot,
    *,
    show_all: bool,
    as_json: bool,
    min_confidence: Confidence,
    compact: bool = False,
) -> str:
    if as_json:
        data = snap.to_dict()
        if not show_all:
            data.pop("sensors", None)
        return json.dumps(data, separators=(",", ":")) if compact else json.dumps(data, indent=2)
    text = format_summary(snap, min_confidence)
    if show_all:
        text += "\n\n" + format_sensors(snap.sensors)
    return text


def _print_debug_report() -> None:
    for line in detection.debug_report():
        print(f"[debug] {line}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Never raises for missing sensors; returns 0."""
    parser = build_parser()
    args = parser.parse_args(argv)
    min_confidence = Confidence(args.min_confidence)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="[debug] %(name)s: %(message)s")
        _print_debug_report()

    try:
        if args.watch is None:
            snap = api.snapshot(min_confidence)
            print(render(snap, show_all=args.all, as_json=args.json, min_confidence=min_confidence))
            return 0
        return _watch(args.watch, args.all, args.json, min_confidence)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # degrade instead of crashing
        if args.debug:
            raise
        print(f"thermals: error: {exc}", file=sys.stderr)
        return 1


def _watch(interval: float, show_all: bool, as_json: bool, min_confidence: Confidence) -> int:
    interval = max(0.1, interval)
    interactive = sys.stdout.isatty() and not as_json
    while True:
        started = time.monotonic()
        snap = api.snapshot(min_confidence)
        text = render(
            snap, show_all=show_all, as_json=as_json, min_confidence=min_confidence, compact=True
        )
        if interactive:
            sys.stdout.write("\x1b[2J\x1b[H")
            stamp = time.strftime("%H:%M:%S")
            sys.stdout.write(f"thermals --watch {interval:g}s   {stamp}   (Ctrl-C to exit)\n\n")
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, interval - elapsed))
