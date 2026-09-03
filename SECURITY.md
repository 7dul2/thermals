# Security Policy

## Scope and guarantees

thermals is a **read-only monitoring library**. It:

* never writes to the SMC, embedded controller, MSRs, BIOS/UEFI or any driver;
* never changes fan speeds, voltages, clocks or power limits;
* never requests elevated privileges (the `powermetrics` backend is used only
  when the process already runs as root);
* never sends data anywhere. There is no telemetry.

On Windows it executes PowerShell `Get-CimInstance` queries against local WMI
namespaces and, optionally, performs an HTTP GET against the LibreHardwareMonitor
web server URL configured through `THERMALS_LHM_URL`. It never executes content
obtained from those sources.

On macOS it opens the `AppleSMC` IOKit service read-only and uses the
`IOHIDEventSystemClient` interface to *read* sensor events.

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's
[security advisory](https://github.com/7dul2/thermals/security/advisories/new)
form rather than a public issue. Include the platform, thermals version and a
reproduction. You can expect an acknowledgement within a week.
