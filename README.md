# thermals

Cross-platform CPU, GPU and SoC temperatures and system thermal state for Python.
Zero dependencies, read-only, honest about what each number means.

```bash
pip install thermals
thermals
```

```
CPU Package        52.4 °C
CPU Core Max       55.1 °C
GPU                43.8 °C
Thermal State     Nominal
Source            hwmon
```

```python
import thermals

print(thermals.cpu_temperature())  # 52.4  (float or None)

reading = thermals.cpu()
print(reading.value)  # 52.4
print(reading.kind)  # SensorKind.CPU_PACKAGE
print(reading.source)  # "hwmon"
print(reading.confidence)  # Confidence.HIGH
print(thermals.thermal_state())  # ThermalState.NOMINAL
```

> **Status:** pre-release. The `v0.1.0` tag and the PyPI upload follow once the
> release checklist in [CHANGELOG.md](CHANGELOG.md) is complete. Until then
> install from GitHub: `pip install git+https://github.com/7dul2/thermals`.

## Why

Python has no unified thermal API. `psutil.sensors_temperatures()` covers Linux
only. Windows has no reliable CPU temperature WinAPI, and ACPI thermal zones are
often not the CPU at all. macOS prefers to publish *thermal pressure* rather than
degrees, and precise Apple Silicon readings live behind undocumented interfaces.

thermals is an abstraction layer with three rules:

1. **Semantics are preserved.** An Intel package sensor, an AMD `Tctl`, an ACPI
   thermal zone and an Apple SoC die sensor are different things and are labelled
   as such (`SensorKind`).
2. **Every reading carries a confidence.** `HIGH` when the driver documents the
   sensor, `MEDIUM` for well-established conventions, `LOW` for firmware zones and
   board headers. The simple API never returns a `LOW` reading unless you ask.
3. **Read-only, never crashes.** No fan, voltage, SMC or EC writes. A missing
   sensor yields `None` plus a reason, not a traceback.

## Installation

Requires Python 3.10 or newer. The core package has no dependencies.

```bash
pip install thermals                                   # after the PyPI release
pip install git+https://github.com/7dul2/thermals      # from GitHub
```

Per-platform notes:

* **Linux**: nothing to install. Reads `/sys/class/hwmon` and `/sys/class/thermal`
  directly; `lm-sensors` is not required.
* **Windows**: install and run [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor).
  thermals attaches to the running instance through its WMI provider (or its
  optional web server, see `THERMALS_LHM_URL`). Without it only low-confidence ACPI
  thermal zones are available.
* **macOS**: nothing to install. Thermal pressure uses Apple's public API; degree
  readings come from the SMC and IOHID (experimental, see below).

## Quick start

```bash
thermals              # summary
thermals --all        # every sensor with kind, confidence and source
thermals --json       # machine readable
thermals --watch      # refresh every second (Ctrl-C to stop)
thermals --watch 0.5  # custom interval
thermals --debug      # show backend probing on stderr
python -m thermals    # same as `thermals`
```

## Platform support

Status as of this commit. "experimental" means the backend depends on
undocumented interfaces that a future OS update may break.

| Feature                 | Linux                    | Windows                         | macOS Intel        | macOS Apple Silicon         |
|-------------------------|--------------------------|---------------------------------|--------------------|-----------------------------|
| CPU temperature         | ✓ hwmon                  | ✓ with LibreHardwareMonitor     | experimental (SMC) | experimental (SMC)          |
| CPU package             | ✓ coretemp               | ✓                               | experimental       | — (die sensors instead)     |
| CPU core / die          | ✓ coretemp, k10temp      | ✓                               | experimental       | experimental (P/E clusters) |
| GPU temperature         | ✓ amdgpu, radeon, nouveau, i915 | ✓                        | experimental       | experimental                |
| Thermal pressure        | —                        | —                               | ✓                  | ✓                           |
| Sensor enumeration      | ✓                        | ✓                               | experimental       | experimental                |
| Low-confidence fallback | thermal zones            | ACPI thermal zones              | —                  | IOHID SoC die sensors       |
| Verified on real hardware | CI fixtures only       | fixtures only, real test pending| fixtures only      | ✓ Apple M5, macOS 26.6      |

Details and known gaps:

* **Linux** supports `coretemp`, `k10temp`, `zenpower`, AMD/Intel/Nouveau GPU
  hwmon drivers, ARM `cpu-thermal`/`soc-thermal` zones and generic label
  heuristics for board drivers. The NVIDIA proprietary driver exposes no hwmon
  temperature; NVML support is not implemented.
* **Windows** does not load `LibreHardwareMonitorLib.dll` in-process. That would
  need pythonnet, a .NET runtime, administrator rights for the kernel driver and
  redistribution of the DLL. Attaching to the running application avoids all of
  that. ACPI zones are reported as `thermal_zone` / `LOW` and are never presented
  as the CPU temperature by default.
* **macOS thermal pressure** maps `NSProcessInfo.thermalState` to
  `nominal` / `fair` / `serious` / `critical` (Apple's own names).
* **Apple Silicon** degree readings are read from the SMC through IOKit (no root
  required). Key prefixes `Tp`/`Te` (P/E cores) and `Tg` (GPU) were verified under
  load on an M5: `Tp` reached 100 °C during a CPU burn while battery keys did not
  move. M1 to M4 use the same prefixes according to community tooling, but were
  not verified by the maintainers. Confidence is capped at `MEDIUM`.
* The IOHID backend exposes `PMU tdie*` SoC die sensors. On M2 to M4 it also
  exposes `pACC`/`eACC`/`GPU MTR` sensors which are mapped to CPU/GPU; on M5 with
  macOS 26 those names are absent, so IOHID only contributes `soc` readings.
* `powermetrics` is used only when running as root.

## API

```python
import thermals
from thermals import Confidence, SensorKind, ThermalState

thermals.cpu_temperature() -> float | None
thermals.gpu_temperature() -> float | None
thermals.cpu()             -> TemperatureReading
thermals.gpu()             -> TemperatureReading
thermals.sensors()         -> list[TemperatureReading]
thermals.thermal_state()   -> ThermalState
thermals.snapshot()        -> Snapshot          # cpu, gpu, thermal_state, sensors, backends
thermals.backend()         -> str | None        # primary backend name, e.g. "hwmon"
thermals.list_backends()   -> list[BackendInfo] # every backend and why it is (un)available
```

`TemperatureReading` fields:

| Field        | Meaning                                                          |
|--------------|------------------------------------------------------------------|
| `value`      | degrees Celsius, or `None`                                       |
| `kind`       | `SensorKind` (what was measured)                                 |
| `source`     | backend that produced it (`hwmon`, `librehardwaremonitor`, `applesmc`, ...) |
| `name`       | original sensor name (`coretemp Package id 0`, `CPU Package`, `GPU (Tg0G)`) |
| `confidence` | `Confidence.HIGH` / `MEDIUM` / `LOW`                             |
| `reason`     | why `value` is `None`, when it is                                |

`cpu()`, `gpu()`, `cpu_temperature()`, `gpu_temperature()` and `snapshot()`
accept `min_confidence=` (default `Confidence.MEDIUM`). Pass
`Confidence.LOW` to accept ACPI thermal zones and board headers.

Example of a degraded result:

```python
>>> thermals.cpu()
TemperatureReading(value=None, kind=<SensorKind.UNKNOWN: 'unknown'>, source='acpi',
    name=None, confidence=<Confidence.LOW: 'low'>,
    reason='Only low-confidence CPU sensors available (thermal_zone/low from acpi); '
           'pass min_confidence=Confidence.LOW to use them')
```

Custom or additional backends can be injected with
`thermals.detection.set_backends([...])`; subclass
`thermals.backends.ThermalBackend`.

## CLI

```
thermals [--all] [--json] [--watch [SECONDS]] [--min-confidence {high,medium,low}] [--debug] [--version]
```

`--json` output (add `--all` to include the `sensors` array):

```json
{
  "cpu": {
    "temperature": 52.4,
    "unit": "C",
    "kind": "cpu_package",
    "source": "hwmon",
    "name": "coretemp Package id 0",
    "confidence": "high",
    "reason": null
  },
  "gpu": { "temperature": 43.8, "kind": "gpu", "source": "hwmon", "confidence": "high", "...": "..." },
  "thermal_state": "unknown",
  "backend": "hwmon",
  "backends": [ { "name": "hwmon", "available": true, "stability": "stable", "detail": null } ],
  "timestamp": 1788000000.0
}
```

In `--watch --json` mode one compact JSON document is printed per line.
The exit code is always `0` unless an unexpected internal error occurs (`1`).

## Sensor semantics

`SensorKind` values and typical sources:

| Kind           | Meaning                                              | Examples                                   |
|----------------|------------------------------------------------------|--------------------------------------------|
| `cpu_package`  | whole CPU package                                    | `Package id 0`, LHM `CPU Package`, `x86_pkg_temp` |
| `cpu_core`     | one core                                             | `Core 3`, LHM `CPU Core #4`                |
| `cpu_die`      | die / chiplet / core cluster                         | `Tdie`, `Tccd1`, LHM `Core (Tctl/Tdie)`, SMC `Tp*`/`Te*` |
| `cpu_control`  | firmware control temperature, may carry an offset    | `Tctl`                                     |
| `gpu`          | GPU edge / core (hotspots keep their name)           | `amdgpu edge`, LHM `GPU Core`, SMC `Tg*`   |
| `soc`          | SoC die not attributable to CPU or GPU               | `PMU tdie3`, `soc-thermal`                 |
| `thermal_zone` | firmware zone, location vendor defined               | `acpitz`, `MSAcpi_ThermalZoneTemperature`  |
| `unknown`      | exists, meaning not determined                       | NVMe, battery, board headers               |

How the CPU value is chosen (`thermals.CPU_KIND_PRIORITY`):

1. Kinds are tried in order: `cpu_package`, `cpu_die`, `cpu_core`,
   `cpu_control`, `soc`, `thermal_zone`.
2. Readings below `min_confidence` are skipped.
3. Within a kind the highest confidence tier is used, and the hottest sensor of
   that tier wins (so per-core sensors yield the maximum core temperature).

`Confidence` describes how certain the *label* is, not the accuracy of the
number. A `LOW` ACPI reading of 27.8 °C is a real measurement of something; it
is just not known to be the CPU.

## Limitations

* No NVIDIA temperatures on Linux without hwmon support (NVML not implemented).
* Windows needs LibreHardwareMonitor running; there is no zero-setup CPU
  temperature on Windows because the OS provides none.
* Windows queries go through PowerShell and take a few hundred milliseconds.
  Results are cached for 0.5 s; use `snapshot()` to read everything at once.
* Apple Silicon degree readings depend on undocumented interfaces and
  heuristic key mapping. Chip generations other than M5 are mapped from
  community knowledge and not verified by the maintainers.
* Thermal pressure is macOS only.
* No fan speeds, power limits, voltages, SMART or battery data (by design).

## Security

thermals is strictly read-only. It never writes to the SMC, EC, MSRs, BIOS or
any driver, never changes fan curves, voltages or power limits, and collects no
telemetry. See [SECURITY.md](SECURITY.md) for reporting.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Backend fixtures from real machines
(especially Windows and older Apple Silicon generations) are the most valuable
contribution right now.

```bash
git clone https://github.com/7dul2/thermals && cd thermals
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
pytest -m hardware   # on a real machine
```

## License

MIT. thermals contains no third-party sensor code; it talks to system
interfaces (sysfs, WMI, IOKit) or to a separately installed
LibreHardwareMonitor process.
