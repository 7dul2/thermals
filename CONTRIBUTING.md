# Contributing

Thanks for helping make thermals more accurate. The most useful contributions
are **sensor fixtures from real machines** and **backend fixes**.

## Development setup

```bash
git clone https://github.com/7dul2/thermals
cd thermals
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Quality gate (also run by CI on Linux, Windows and macOS):

```bash
ruff check .
ruff format --check .
mypy
pytest                 # unit tests, no hardware needed
pytest -m hardware     # real sensors on this machine (optional)
python -m thermals --debug
```

## Project layout

```
thermals/
  api.py            public functions and CPU/GPU selection rules
  cli.py            `thermals` command
  models.py         dataclasses and enums
  detection.py      platform -> backend list
  backends/
    base.py         ThermalBackend interface
    linux/          hwmon, thermal_zone
    windows/        libre_hardware_monitor, acpi
    macos/          thermal_pressure, smc, apple_silicon (IOHID), powermetrics
tests/
  fixtures/         sysfs trees, WMI/HTTP JSON, SMC/IOHID captures
```

## Adding or fixing a backend

1. Subclass `thermals.backends.base.ThermalBackend`. Implement `available()`
   (must not raise), `sensors()` and optionally `thermal_state()`. Explain
   unavailability in `detail()`.
2. Keep the raw sensor meaning: choose the most specific `SensorKind` and be
   conservative with `Confidence`. `HIGH` is reserved for documented driver
   semantics. When in doubt use `UNKNOWN`/`LOW`; the reading still shows up
   in `thermals --all`.
3. Never write to hardware. Backends are read-only by contract.
4. Make the low-level reader injectable (`reader=`, `runner=`) so the mapping
   logic is unit-testable without hardware.
5. Add fixtures under `tests/fixtures/<platform>/` and tests next to the
   existing ones. Fixtures should be real captures where possible; note the
   machine model in the file.
6. Register the backend in `thermals/detection.py` and document it in the
   README support matrix truthfully.

### Capturing fixtures

* Linux: `tar czf hwmon.tgz -h /sys/class/hwmon` (follow symlinks) or copy
  `name`, `temp*_input`, `temp*_label` files; `thermal_zone*/type` + `temp`.
* Windows: with LibreHardwareMonitor running, run the PowerShell snippet in
  `thermals/backends/windows/libre_hardware_monitor.py` (`WMI_SCRIPT`) and save
  the JSON, or fetch `http://localhost:8085/data.json`.
* macOS: `python -c "from thermals.backends.macos.smc import SMCClient; print(SMCClient().read_temperatures())"`
  and the same for `thermals.backends.macos.apple_silicon.HIDTemperatureReader`.

## Third-party code and licenses

Do not copy code from other sensor projects. Before linking, vendoring or
porting anything, check its license and record the decision in the pull
request. thermals talks to system interfaces directly so that it stays MIT.

## Commits and pull requests

Use conventional commit prefixes: `feat(linux): ...`, `fix(macos): ...`,
`test: ...`, `docs: ...`, `chore: ...`. Keep commits focused on one change.
Every pull request must pass the quality gate above.
