# 1.7.2 automation-lock correction

Pending automatic wakes now stop when the automation lock is enabled, while explicit manual control remains available. Tests reproduce lock activation before task execution, during the startup delay, and while intent waits behind another control transaction. Manual supersession is covered separately. Supply startup timing is documented in [STANDBY.md](STANDBY.md).

The following notes describe the previous consolidated baseline.

# 1.7.1

Consolidates the installed AV implementation and published 1.6.3 changes. Preserves configured routes and devices. Improves Apple TV power acknowledgment, source metadata and arbitration so newer user actions take precedence over pending operations.

Validation: 337 Python tests pass on Home Assistant 2025.3.4 and 2026.9.4, and in an isolated 2026.10.4 container. The minimum-version run also passes against LG 2.0.0. Existing installed component files and settings were verified unchanged. Physical device actions were not repeated for this repository consolidation.
