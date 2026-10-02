# Isolated Docker acceptance harness

Use a disposable Home Assistant test instance. These scripts create/configure test entities and deliberately switch simulated power and sources. They require `aiohttp`; install `requirements-test.txt` in a local venv. They must never be pointed at a configured production AV system.

1. Install both custom components in HA. Copy `dev/av_test_lab` as `custom_components/av_test_lab` **only in the test installation**. This fixture is not included by HACS. Restart HA.
2. Run `python dev/lg_simulator.py` on the Docker host. TCP port 18761 is exposed for the container; test control HTTP 18762 binds only localhost. Use a trusted test network/firewall.
3. In HA add **LG Professional Display**, host `host.docker.internal`, port `18761`, name **LG Split Test**. Linux Docker may require `extra_hosts: ["host.docker.internal:host-gateway"]`. Expected entity: `media_player.lg_split_test_display`.
4. Export `HA_TOKEN` with a test-only long-lived HA token; optionally set `HA_URL` (default `http://127.0.0.1:8123`). Do not commit tokens.
5. Run `python dev/configure_av.py`. It creates fixture and AV entries and links only `av_test_*` entities. Expected AV entity: `media_player.av_split_test_av_system`. Use a clean registry so names have no numeric suffixes.
6. Run `python dev/test_container.py`. Allow approximately three minutes for real timer windows. Results are written to ignored `dev/results.json`. On failure inspect HA logs and the assertion, fix the cause, and rerun. Do not shorten production standby thresholds below their validated options range.
7. Remove AV Split Test, LG Split Test and AV Test Fixtures entries, stop the simulator and remove only the copied `av_test_lab` fixture directory. Keep the two actual integration packages if desired.

The harness uses actual config flows, HA entity service handlers, WebSocket management and TCP commands. It never needs an LG password. Native web/media hardware acceptance is separate and described in `docs/TESTING.md`. A fixture-backed HomeKit event test does not pair an iPhone or reproduce tvOS/CEC behavior.
