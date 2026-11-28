# AGENTS.md

Guidance for AI coding agents (and humans) working on **viessmann-optolink2mqtt**: a long-running Python
daemon that talks to a Viessmann heating device (heat pump, gas boiler, ...) over the **Optolink** serial
interface using the **VS2 / "300" protocol**, and bridges its registers to **MQTT**, with optional
**Home Assistant** MQTT discovery.

User documentation is in [README.md](README.md); the annotated reference configuration is
[optolink2mqtt.yaml](optolink2mqtt.yaml).

## Use the Makefile

**Use the `Makefile` targets whenever one does what you need, instead of typing the underlying
commands.** `make` is pre-authorized for agents in `.claude/settings.json`, so targets run without
permission prompts, and they always use the right tools and flags. `make help` lists every target.

| Task | Command |
|---|---|
| Set up the dev environment (once) | `make dev-setup`: creates `.venv` with the runtime deps, pytest, black, flake8, ruff and build. The other targets use `.venv` automatically, no activation needed. |
| Check everything before committing | `make check`: black formatting check, ruff, flake8 and the unit tests, like CI |
| Format the code | `make format` (rewrites files with black) |
| Check formatting only | `make format-check` |
| Lint | `make lint` (ruff + flake8) |
| Run the unit tests | `make test`; filter with `make test REGEX=read_register` (a `pytest -k` expression) |
| Lint the GitHub Actions workflows | `make lint-workflows` (needs `actionlint`) |
| Build / inspect the wheel | `make build-wheel`, `make test-wheel` (rebuilds and installs it), `make inspect-wheel` |
| Run the app from the checkout | `make run-from-local-git-clone ARGS="--help"` |
| Clean build artifacts and caches | `make clean` |

Fall back to raw commands only when no target fits, for example to run a single test file:
`.venv/bin/pytest -q tests/test_config.py`. If a command keeps coming up, add a target for it rather
than repeating it.

`flake8` ignores line length (E501) and E203, so black decides the layout. CI
(`.github/workflows/main.yml`) runs flake8 and the unit tests, and must pass.

Don't use these targets unattended: `make test-hw` talks to a real device (read-only, but
see [Safety rules](#safety-rules-for-agents)), and the `docker-*` targets build images and start
containers.

## Repository map

| Path | What it is |
|---|---|
| `src/optolink2mqtt/main.py` | Entry point (`optolink2mqtt` console script). Parses the CLI and dispatches to a mode. |
| `src/optolink2mqtt/cli.py` | argparse definition of the modes: `run` (default when no mode is given) and `read-register`. |
| `src/optolink2mqtt/optolink2mqtt_app.py` | `Optolink2MqttApp`: the `run` mode. Setup, scheduler, main loop, error recovery, shutdown. |
| `src/optolink2mqtt/read_register.py` | The `read-register` mode: reads one register once and prints a report, for reverse-engineering. |
| `src/optolink2mqtt/optolink_interface.py` | `OptolinkInterface`: owns the serial port and the protocol instance; connect, reconnect policy, register read/write, failure counting. |
| `src/optolink2mqtt/optolinkvs2_protocol.py` | `OptolinkVS2Protocol`: VS2 handshake, telegram encoding, CRC, response parsing/validation, per-`ErrorCode` statistics. No knowledge of registers or MQTT. |
| `src/optolink2mqtt/optolinkvs2_register.py` | `OptolinkVS2Register`: register **metadata** (address, length, type, signed, scale, byte filter, enum, HA discovery) and raw bytes <-> value conversion. Stores no value. |
| `src/optolink2mqtt/datetime_bcd.py` | Codec of the 8-byte Viessmann DateTimeBCD format, and IANA timezone lookup for `optolink.timezone`. |
| `src/optolink2mqtt/mqtt_client.py` | `MqttClient`: thin wrapper over `paho.mqtt.client` (connection, last will, callbacks, counters). |
| `src/optolink2mqtt/enhanced_mqtt_client.py` | `EnhancedMqttClient`: `MqttClient` plus Home Assistant discovery and optolink2mqtt status/metrics topics. |
| `src/optolink2mqtt/config.py` | `Config`: finds, loads and validates the YAML config, then fills every optional key with its default. |
| `src/optolink2mqtt/schema/optolink2mqtt.schema.yaml` | [yamale](https://github.com/23andMe/Yamale) schema of the config file. |
| `src/optolink2mqtt/ha_support.py`, `ha_units.py` | Home Assistant platforms, device classes, state classes and units accepted in the config. |
| `src/optolink2mqtt/_optolink2mqtt_version.py` | **Generated** by hatch-vcs at build time and gitignored. Do not create or edit it. |
| `tests/` | pytest suite, one `test_<topic>.py` per area. No hardware needed (see [Testing](#testing)). |
| `docs/config-upgrade/` | Static page (GitHub Pages) converting config files to the latest `config_version`; the conversions are in `migrations.js`. |
| `optolink2mqtt.yaml` | Reference config: every option, commented, with its default value. Also loaded by tests. |
| `Makefile` | Development targets (`make help`): setup, format, lint, test, build. Use them, see [Use the Makefile](#use-the-makefile). |
| `.claude/settings.json` | Commands pre-authorized for agents (`make`, `actionlint`, `black --check`, `docker info`). |
| `Dockerfile`, `docker-compose.yml` | Container image (Alpine, non-root user in `dialout`). |
| `pyproject.toml`, `requirements.txt` | Packaging (hatchling + hatch-vcs). `requirements.txt` **is** the package's dependency list (via hatch-requirements-txt). |

## Architecture

### `run` mode data flow

```text
             paho network thread                         main thread
MQTT broker ───────────────────> MqttClient.on_message ──> queue.Queue (bounded, put_nowait)
     ^                                                            │
     │                                                            v
     └──── EnhancedMqttClient.publish <── Optolink2MqttApp._core_loop ──> sched.scheduler (time.monotonic)
                                                  │
                                                  v
                       OptolinkInterface ──> OptolinkVS2Protocol ──> serial port (4800 baud, 8E2, exclusive)
```

- **Two threads only.** The paho network thread (started by `loop_start()`) runs the MQTT callbacks.
  The main thread does everything else: scheduling, every serial access, every register read and write.
- **MQTT callbacks never block and never raise.** They hand incoming messages to the main thread via a
  bounded `queue.Queue` with `put_nowait` (messages are dropped and counted when it is full), and set
  flags guarded by locks. An exception there would kill the paho thread.
- **Polling** is a `sched.scheduler` on `time.monotonic`. Entries with the same register address and
  length form a *read group* (`Optolink2MqttApp.read_groups`): the register is read once per poll and
  decoded for every entry. Each group timer re-enqueues itself (`on_schedule_timer`); initial reads are
  staggered by 100 ms. A write received over MQTT is followed by a read-back of the register's group,
  scheduled at high priority, so other clients see the real value.
- **`_core_loop`** wakes at least every 0.5 s: runs due scheduler events, waits on the queue until the
  next event, processes at most one MQTT message per iteration.
- **Recovery** happens in `_main_loop`:
  - serial, `termios` and Optolink errors go through `OptolinkInterface.handle_serial_error()`, which closes
    the port and returns the delay before reconnecting (`reconnect_period_sec`), or `None` once
    `reconnect_timeout_sec` expires (0 = retry forever), and the app exits;
  - `max_consecutive_failures_before_reinit` failed reads in a row raise
    `OptolinkReinitializationRequired`, which re-runs the VS2 handshake;
  - MQTT reconnection is left to paho; on a disconnect the main loop just waits
    `mqtt.reconnect_period_sec` and resumes.
- **Shutdown**: SIGTERM/SIGINT call `request_stop()`, which sets a `threading.Event`. Every wait in the
  main loop goes through that event, so the app stops promptly, publishes `offline` and disconnects.

### Protocol layer

- `OptolinkVS2Protocol.read_datapoint_ext()` / `write_datapoint_ext()` return an `OptolinkVS2RxData`
  carrying an `ErrorCode`. Protocol failures are **return values, not exceptions**; only the serial
  port itself raises (`serial.SerialException`, `termios.error`). Every outcome is counted in
  `stats_by_receive_code`.
- Responses are validated (STX, length, CRC, message type, address). Requests whose address or length
  cannot be encoded are refused with `ErrorCode.InvalidRequest` without touching the port.
- The serial port is opened with `exclusive=True` (an `flock`): only one process can talk to the device.
  `read-register` relies on this to bail out (exit code 5) when a `run` instance holds the port.

### Registers and MQTT topics

- The register `type` alone decides how bytes are decoded; `ha_discovery` only shapes what Home Assistant
  sees, never the decoding. Types:
  - `int` (default): integer, optionally `signed`, little-endian unless `encoding: big_endian`;
  - `float`: the same integer multiplied by `scale_factor` (allowed only for this type) and rounded to
    2 decimals;
  - `enum`: the integer mapped to a label by the `enum` dictionary (and back, for writes);
  - `datetime_bcd`: 8 BCD bytes `CC YY MM DD WW hh mm ss` (weekday 0=Monday) in device local time,
    published as ISO 8601 with the UTC offset of `optolink.timezone` (host timezone by default), or
    `None` for the "not set" value 1970-01-01.

  `byte_filter` (`"b:<start>:<end>"`, both inclusive) decodes a slice of an `int` or `float` register.
  `formatter` is a Jinja2 template, rendered in a `SandboxedEnvironment` with the decoded value as `x`,
  whose output is published instead of the value; it is compiled at startup and refused on writable
  registers. `same_read_as: <name>` copies `register` and `length` from another entry (resolved in
  `Config._resolve_same_read_as()`); entries of a read group must share `sampling_period_seconds`.
- Topics: state `<publish_topic_prefix>/<sanitized name>`, command `<publish_topic_prefix>/<sanitized name>/set`
  (subscribed only for `writable` registers). Names are sanitized to `[a-z0-9_]`; two registers
  mapping to the same topic are rejected at startup.
- Diagnostics are published under `optolink2mqtt_status` (`online`/`offline`, also the MQTT last will),
  with the Optolink connection state and error/disconnect counters below it.
- HA discovery messages are (re)published on every new broker connection and whenever Home Assistant
  announces `online`; register values are then republished too.

### Configuration

- Lookup order: `$OPTOLINK2MQTT_CONFIG`, then the user config dir, then `/etc/optolink2mqtt/`
  (see `Config.get_default_config_file_name()`). The schema location can be overridden with
  `$OPTOLINK2MQTT_CONFIGSCHEMA`. `MQTT_BROKER_PASSWORD` / `MQTT_BROKER_PASSWORD_FILE` override the broker password.
- After `Config.load()` every optional key of the `logging`, `optolink`, `mqtt` sections and of each
  register exists, set to its default or `None`, so code reads `config["section"]["key"]` directly.
  Defaults live only in `Config._fill_defaults_*()`, never as fallbacks scattered in the code.
  Exception: some `ha_discovery` keys of a register (`min`, `max`, `step`, `mode`, ...) may be missing
  and are read with `.get()`.
- Startup validates everything up front and fails fast with a distinct exit code; at runtime, invalid
  input is logged and skipped.

### Exit codes

| Mode | Code | Meaning |
|---|---|---|
| `run` | 0 | stopped on request (SIGTERM/SIGINT) |
| `run` | 1 | Optolink errors persisted beyond `reconnect_timeout_sec` |
| `run` / `read-register` | 2 | configuration cannot be loaded (`run`: also VS2 handshake never succeeded before the timeout) |
| `run` | 3 | no registers to poll |
| `run` / `read-register` | 4 | invalid register definition |
| `read-register` | 5 / 6 / 7 | serial port busy / Optolink connection failed / read failed |

Exit codes are part of the interface (systemd units, scripts, Docker restart policies): don't renumber them.

## Design principles

1. **Run unattended 24/7.** Never crash on bad input: malformed MQTT payloads, out-of-range values,
   garbage from the serial line. Validate, log, count, and keep going. Recover from serial and network
   failures instead of exiting, unless the configured timeouts say otherwise.
2. **The heating system is the priority.** Be conservative with Optolink traffic: one request at a
   time, only from the main thread, never from MQTT callbacks. Some devices fail to boot when there is
   Optolink traffic during a power cycle (issue #37), hence the long default `reconnect_period_sec`.
3. **MQTT input is untrusted.** Any client can publish on a command topic: writes go through
   `get_rawdata_from_value()` and `is_within_write_bounds()` (HA `min`/`max`), and only to registers
   declared `writable`.
4. **Fail fast at startup, degrade gracefully at runtime.** Configuration and register definitions are
   fully validated before the first serial byte is sent.
5. **Keep layers separate.** The protocol knows nothing about registers or MQTT; registers know nothing
   about the serial port; the app orchestrates. Reuse these layers for new features, as
   `read-register` does, instead of duplicating serial or decoding logic.
6. **Stay backward compatible.** Users' Home Assistant dashboards and automations depend on config
   keys, MQTT topic names, HA `unique_id`s (`<device_name>-<sanitized name>-<address>`), CLI modes and
   exit codes. Changing any of them is a breaking change: avoid it, or call it out explicitly.
7. **Stay compatible with Python 3.9** (`requires-python = ">=3.9"`), to support Debian 11 and its
   derivatives. Use `from __future__ import annotations` in modules with `X | None` annotations; don't
   use `match`, `tomllib` or other 3.10+ features in `src/`. Before bumping a dependency in
   `requirements.txt`, check that its `Requires-Python` still allows 3.9.
8. **Minimal dependencies.** Five runtime dependencies (pyserial, paho-mqtt, yamale, platformdirs, Jinja2).
   Prefer the standard library; adding a dependency needs a strong reason.
9. **Monotonic time** for every delay and timeout (`time.monotonic()`): the wall clock jumps on
   single-board computers without an RTC.

## How to make common changes

- **New config option**: add it to the schema (`schema/optolink2mqtt.schema.yaml`), give it a default
  in the matching `Config._fill_defaults_*()` method, document it in `optolink2mqtt.yaml` (commented,
  showing the default), mention it in the README if users need to know, and add a test.
- **Breaking config change**: bump `Config.CONFIG_VERSION` in `config.py` and `config_version` in
  `optolink2mqtt.yaml`, then add the conversion from the previous version to `MIGRATIONS` in
  `docs/config-upgrade/migrations.js` and bump its `LATEST_VERSION`. Each release accepts only its own
  version; files without `config_version` are version 1.
- **New Home Assistant discovery field**: add it to `register_ha_discovery` in the schema **and** to
  `optional_parameters` in `OptolinkVS2Register.get_ha_discovery_payload()`; new accepted values go in
  `ha_support.py` / `ha_units.py`.
- **New CLI mode**: add a subparser in `cli.py`, a module implementing it, and a branch in `main.py`.
  Keep `run` the default when no mode is given.
- **New source file**: start it with the same module docstring header (file name, one-line purpose,
  copyright, GPLv3 notice) as the existing files. The Docker image copies `src/optolink2mqtt/*.py` flat
  into `/opt/optolink2mqtt/src/` and runs `python -m src.main`, so:
  - use **relative imports** inside the package (`from .config import Config`);
  - non-Python files (like the schema) must be copied explicitly in the `Dockerfile`.
- **Protocol changes**: follow the references in the `OptolinkVS2Protocol` docstring, and test telegram
  bytes exactly (see `tests/test_optolinkvs2_protocol_mocked.py`).

## Testing

- Every behavior change or bug fix comes with a test. Tests must not need hardware or a broker.
- Each test file makes the sources importable with the same preamble, then imports `optolink2mqtt.*`:

  ```python
  THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
  SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
  sys.path.append(SRC_DIR)
  from optolink2mqtt.config import Config  # noqa: E402
  ```

- Serial port: use a `unittest.mock.Mock` with `read`/`read_all`/`write` side effects
  (`tests/test_optolinkvs2_protocol_mocked.py`), or the `FakeVS2Device` that answers on a pseudo-terminal
  (`tests/test_read_register_mode.py`) for end-to-end tests.
- MQTT: mock the paho client; nothing connects to a real broker.
- Tests calling `Optolink2MqttApp.setup()` monkeypatch `sys.argv` and
  `Optolink2MqttApp.get_embedded_version` (the generated version file may be missing in a checkout).
- `tests/test_optolinkvs2_protocol.py` is the only hardware test. It is skipped unless
  `OPTOLINK2MQTT_TEST_SERIAL_PORT` is set (`make test-hw SERIAL_PORT=/dev/ttyUSB0`), and it only
  **reads** registers.
- Run the suite with `make test`, or a subset with `make test REGEX=<pytest -k expression>`.

## Safety rules for agents

- **Never write to a real device.** Don't run write commands or tests against real hardware, and never
  publish on a `.../set` topic of a live installation: a wrong value can change how a heating system
  behaves. To explore a device, use `optolink2mqtt read-register`, which only reads.
- Don't commit secrets: MQTT credentials belong in environment variables or local config files, not in
  `optolink2mqtt.yaml` or tests.
- Don't edit generated files (`_optolink2mqtt_version.py`).

## Commits and pull requests

- One logical change per PR, with its tests and doc updates.
- `make check` must pass before committing.
- Commit titles are imperative sentences that describe the behavior change, e.g.
  "Reject malformed MQTT write payloads instead of crashing" or
  "Use a monotonic clock for the register scheduler and protocol timeouts".
- User-facing changes update the README and, for config changes, `optolink2mqtt.yaml`.
- Releases are cut by pushing a tag: the version comes from git (hatch-vcs), and
  `.github/workflows/pypi-release.yml` publishes to PyPI.
