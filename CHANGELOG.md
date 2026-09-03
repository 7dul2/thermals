# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned
- Optional in-process LibreHardwareMonitor backend (pythonnet) as an extra.
- NVML backend for NVIDIA GPUs on Linux.
- `thermals.watch()` iterator and threshold callbacks.
- Prometheus exporter.

## [0.1.0] - Unreleased

Initial release.

### Added
- Data model: `TemperatureReading`, `SensorKind`, `Confidence`, `ThermalState`,
  `Stability`, `BackendInfo`, `Snapshot`.
- Public API: `cpu_temperature()`, `gpu_temperature()`, `cpu()`, `gpu()`,
  `sensors()`, `thermal_state()`, `snapshot()`, `backend()`, `list_backends()`.
- Linux backends: `/sys/class/hwmon` (coretemp, k10temp, zenpower, amdgpu,
  radeon, nouveau, i915, ARM SoC drivers, generic labels) and
  `/sys/class/thermal` zones.
- Windows backends: LibreHardwareMonitor via WMI provider or HTTP `data.json`,
  ACPI `MSAcpi_ThermalZoneTemperature` low-confidence fallback.
- macOS backends: thermal pressure (`NSProcessInfo.thermalState`, stable),
  Apple SMC via IOKit (experimental, Intel and Apple Silicon), IOHID SoC die
  sensors (experimental, Apple Silicon), `powermetrics` (root only).
- CLI: `thermals`, `--all`, `--json`, `--watch [SECONDS]`, `--min-confidence`,
  `--debug`, `--version`; `python -m thermals`.
- Fixture based unit tests for every backend, smoke tests, `-m hardware` tests.
- GitHub Actions CI on Linux, Windows and macOS (arm64).

### Release checklist for v0.1.0
- [x] pytest, ruff, mypy pass
- [x] package builds (`python -m build`)
- [x] CLI runs without hardware
- [x] real macOS Apple Silicon test (Apple M5, macOS 26.6: `pytest -m hardware`)
- [ ] real Windows test with LibreHardwareMonitor running
- [x] Linux backend covered by fixtures and CI
- [x] CI green on ubuntu, windows and macos (arm64) runners for Python 3.10, 3.12, 3.14
- [x] Windows transport (PowerShell/WMI, HTTP) exercised on a real Windows runner without LibreHardwareMonitor: clean degradation, no crash
- [x] README matches actual capabilities
