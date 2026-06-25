# FILE_MANIFEST - The Project Map

Authoritative inventory of every source artifact in the DFX_ate project. Update
this table whenever a file is added, renamed, removed, or has its responsibility
materially changed.

> Synced to the source tree on 2026-06-07 by an external code audit. Files that
> were previously undocumented are flagged **(NEW)**; files whose described
> behaviour no longer matches the code are flagged **(CHANGED)**; non-functional
> artifacts are flagged **(STALE/UNUSED)**.

## Entry point & top-level modules

| File Path                | Module | Short Description                                                                                                  |
| ------------------------ | ------ | ----------------------------------------------------------------------------------------------------------------- |
| `src/main.py`            | entry  | Sets the Windows AppUserModelID, seeds user data, acquires `SingleInstanceLock`, then runs a login → `MainWindow` loop that supports logout-and-switch-user. |
| `src/env.py`             | config | **(NEW)** `.env` loader (`load_env_once()`) + typed getters (`get_str`, `get_bool`, `get_list`). Loads once at import; degrades gracefully if `python-dotenv` is absent. |
| `src/config.py`          | config | Feature flags (`SHOW_LIVE_MONITOR`, `SHOW_SEARCH_BAR`), `UUT_TYPES` list, secrets, and station identity — all sourced from the environment via `env.py`. Zero hardcoded secrets. |
| `src/paths.py`           | config | Dev/frozen path resolution. `resource_path()` for bundled read-only files, `user_data_path()` for writable state, `user_tmp_path()` for scratch files swept on startup, `ensure_user_data_seeded()` to copy seed `.tst`/`limits.json` next to the EXE. |
| `src/version.py`         | config | Single source of truth for `__version__`; reads `APP_VERSION` from `.env` (default `"0.1.0-Beta"`). |

## `src/logic/` — Qt-free business logic (plus the two sanctioned QThreads)

| File Path                       | Short Description                                                                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/logic/__init__.py`         | Package marker.                                                                                                                                    |
| `src/logic/models.py`           | Domain types: `TestLimit` (legacy, frozen slots), `TestStep`, `ScriptDocument` (metadata + steps), `TestResultPayload` `TypedDict`, `TestRunRecord`. |
| `src/logic/test_engine.py`      | `TestRunnerThread(QThread)`. Script-driven runner; loops, retries, `Critical` abort, `stop_on_fail`, cooperative cancel, **pause/resume**, `Prompt` via `threading.Event`, per-result secure logging, and `report_snapshot()` for PDF/CSV. Emits 8 signals. Before each step it calls the driver's optional `set_active_step(unit, min, max)` hook if present (no-op for `MockHardware`; used by test-specific mocks). |
| `src/logic/script_manager.py`   | `ScriptManager`; discovery, raw read/write, `load_document()` parser (→ `ScriptDocument`), and `serialize_ordered_steps()` for version archiving. Recognizes `PartNum:` header, `Critical`, `Limits`, `Target/Tol`, `Unit`, `Retry`. Defines `ScriptParseError`. |
| `src/logic/database_manager.py` | **(CHANGED)** `DatabaseManager`; thin facade over `logic/db/` sub-modules. Holds the class-level `_schema_ready` bootstrap flag. Public API unchanged for all callers. |
| `src/logic/db/__init__.py`      | Package marker for the `logic.db` repository sub-package. |
| `src/logic/db/connection.py`    | `open_conn(db_path)` — shared SQLite connection factory with `row_factory` and `PRAGMA foreign_keys = ON`. |
| `src/logic/db/schema.py`        | `create_tables()` — DDL for the seven tables (incl. global `instrument_connections` and `bench_config`), the idempotent `connection_params` `ALTER TABLE` migration, and `_seed_admin()` bootstrap. |
| `src/logic/db/connections.py`   | Global per-instrument connection strings DAL: `list_connections`, `upsert_connection` (`instrument_connections` table). |
| `src/logic/db/bench_config.py`  | **(NEW, Phase 0; +key Phase 4)** Global bench-wiring key/value DAL: `get_bench_config`, `set_bench_config`; key constants `DAQ_RELAY_CHANNEL`, `LOAD_SLOT`, `DAQ_CHANNEL_MAP` (logical→physical, `"3=103,4=104"`). |
| `src/logic/db/users.py`         | User CRUD: `verify_login`, `create_user`, `delete_user`, `update_user`, `change_password`, `list_users`. |
| `src/logic/db/test_versions.py` | Test-version catalog: `add_test_version`, `list_test_versions`, `get_test_version`, `delete_test_version`, `version_exists`. |
| `src/logic/db/audit.py`         | `log_audit_action` (writes DB row + `SecureLogger` side-channel), `get_audit_logs`. |
| `src/logic/db/test_runs.py`     | `save_run(record: TestRunRecord)` — inserts one `test_runs` row + N `test_results` rows atomically. |
| `src/logic/auth_manager.py`     | `AuthManager`; thin facade over `DatabaseManager.verify_login`/`change_password`. `validate_password_strength()` is defined but **never called**. |
| ~~`src/logic/limit_manager.py`~~ | **DELETED (2026-06-07)** — was STALE/UNUSED. `LimitManager` was not imported anywhere; `limits.json` keys matched no current test names. |
| `src/logic/file_lock.py`        | `SingleInstanceLock`; **Windows:** named mutex via `CreateMutexW` (`Local\DFX_ate_singleton`) — OS releases automatically on process death, no stale-lock logic needed. **POSIX:** PID lock file with `os.kill` liveness probe. |
| `src/logic/secure_logger.py`    | **(NEW)** `SecureLogger`; Fernet-encrypted, append-only daily JSON log (`logs/sys_YYYYMMDD.dat`). Process-wide singleton via `get_secure_logger()`. Key derived from the hardcoded `LOG_ENCRYPTION_PASSWORD`. |
| `src/logic/monitor_engine.py`   | **(NEW)** `MonitorThread(QThread)`; emits simulated voltage/current readings on an interval. **Second QThread in `logic/`** (not covered by the old "only `test_engine` uses QtCore" exception). |
| `src/logic/report_generator.py` | **(NEW)** `ReportGenerator` + module functions; PDF (ReportLab + PyPDF2 logo watermark, admin-only encryption) and CSV reports with role-based detail; auto-archives under `data/results/<UUT>/<Serial>/`. |

## `src/drivers/` — hardware abstraction

| File Path                     | Short Description                                                                                                                                |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/drivers/__init__.py`     | Package marker.                                                                                                                                  |
| `src/drivers/base_driver.py`  | `BaseDriver(ABC)` — real abstract contract (`connect`, `disconnect`, `execute_command`, `measurement_commands` property) plus a non-abstract `identify() -> dict[str, str]` (default `{}`, Phase 0; overridden by `BenchDriver`) and an error hierarchy (`HardwareError`, `ConnectionLostError`, `CommandTimeoutError`, `UnknownCommandError`). |
| `src/drivers/mock_hardware.py`| `MockHardware(BaseDriver)`; Qt-free simulator. `execute_command` handles `setvoltage`, `relay`, `getid`, and `setlogic` as side-effect commands; `readchannel` as a measurement command. `measurement_commands` returns `frozenset({"readchannel"})`. Raises `UnknownCommandError` for unknown commands. `connect()`/`disconnect()` called by the runner lifecycle. **Generic and stateless** — fixed per-channel nominals; it does not track `setvoltage`/`setload`. |
| `src/drivers/mocks/__init__.py` | Package marker for **test-specific** mock drivers (stateful stand-ins for one concrete `.tst` program each, vs. the generic `mock_hardware.py`). Re-exports `SpreosPowerSupplyMock`. |
| `src/drivers/bench/__init__.py` | **(NEW)** Package marker for the bench layer (composite `BenchDriver`, capability contract, factory). |
| `src/drivers/bench/instrument_base.py` | **(NEW, Phase 0)** Device-facing capability layer (Qt-free, no DB): `ConnInfo` descriptor; `runtime_checkable` Protocols `VoltageSource` / `ElectronicLoad` / `Multimeter` / `DiscreteIO`; `InstrumentDriver(ABC)` lifecycle (`is_available` / `open` / `close` / `identify`). Contract only — no transport code yet. |
| `src/drivers/bench/factory.py` | **(UPDATED, Phase 4)** `build_bench(...)` + `build_sim_bench(...)` + `preflight(...)`. Sim path: three coupled mocks (shared `SimBus`). Hardware path: real drivers built from parsed connection strings (`parse_serial`/`parse_visa`/`parse_prologix`/`parse_daq_channel_map`), with `BenchConfigError` listing every missing item. `preflight()` gates on `is_available()` + open/`identify()` and returns a report for the GUI. No hardcoded COM/GPIB/slot/channel. |
| `src/drivers/bench/bench_spec.py` | **(NEW, Phase 4)** Canonical `instrument_connections` name keys for the SPREOS bench (`POWER_SUPPLY`/`DAQ`/`ELECTRONIC_LOAD`, `BENCH_INSTRUMENT_NAMES`). Dependency-light; shared by the factory and the Connections dialog. |
| `src/drivers/bench/bench_driver.py` | **(UPDATED, Phase 4)** `BenchDriver(BaseDriver)` — composes the 3 SPREOS instruments and routes `.tst` commands to capability calls (`setvoltage`→source, `setload`→load CP/power/input, `setlogic`/`relay`→DAQ `DiscreteIO`, `readchannel`+unit→channel map, `getid`→`identify()`). Pure routing; `set_active_step` for V/A; a `daq_channel_map` remaps logical→physical DAQ mux channels. |
| `src/drivers/bench/command_map.py` | **(NEW, Phase 3)** Logical channel→role map (`SPREOS_CHANNEL_MAP`: 1→source, 3/4→dmm, 5→load) + `CURRENT_UNITS`/`wants_current`. Test structure, not a hardware address; per-version map is a later phase. |
| `src/drivers/bench/sim_bus.py` | **(NEW, Phase 3)** `SimBus` (shared `input_voltage`/`load_watts`/`logic_on`) + `reading()` (jitter + occasional out-of-spec). Injected into the mocks (`bus=...`) to couple the Simulation bench; mocks stay isolated when `bus=None`. |
| `src/drivers/bench/transports/__init__.py` | **(NEW, Phase 1)** Package marker for transport wrappers; each guards its optional comms-stack import. |
| `src/drivers/bench/transports/visa.py` | **(NEW, Phase 1)** `VisaSession` (open/query/write/close over pyvisa) + `visa_available()`. pyvisa imported guarded (optional dep); faults mapped to `ConnectionLostError`/`CommandTimeoutError`. |
| `src/drivers/bench/transports/serial_port.py` | **(NEW, Phase 2)** `SerialSession` (RS-232 over pyserial) + `serial_available()`. pyserial imported guarded; parity/stopbits/bytesize config-string→constant mapping; faults mapped to the `HardwareError` hierarchy. |
| `src/drivers/instruments/__init__.py` | **(NEW, Phase 1)** Package marker — one folder per device (real `driver.py` + `mock.py` + `protocol.py` + `README.md`). |
| `src/drivers/instruments/daq_9600/` | **(NEW, Phase 1)** GW Instek DAQ-9600 + DAQ-901. `driver.py` `Daq9600` (VISA; `Multimeter` + `DiscreteIO`; `is_available()` gates on `visa_available()`), `mock.py` `Daq9600Mock`, `protocol.py` (SCPI builders), `README.md`. Minimal `__init__` (no re-exports — avoids a `protocol` import cycle). |
| `src/drivers/instruments/idrc_040_076hr/` | **(NEW, Phase 2)** IDRC-040-076HR programmable DC PS. `driver.py` `IdrcPowerSupply` (RS-232; `VoltageSource` + `set_protection`; `is_available()` gates on `serial_available()`; drives output off on close), `mock.py` `IdrcPowerSupplyMock`, `protocol.py` (SCPI builders — confirmed: IDRC DSP series is standard SCPI), `README.md`. |
| `src/drivers/instruments/prodigit_3300/` | **(NEW, Phase 2)** Prodigit 3300G mainframe + 3315G load. `driver.py` `Prodigit3300Load(load_slot, gpib_address)` (`ElectronicLoad`; **Prologix GPIB-USB** over `SerialSession`; `++mode/++addr/++auto` init then `CHAN n`-routed SCPI; `NAME?` identity + empty-slot probe; input off on close), `mock.py` `Prodigit3300LoadMock`, `protocol.py` (Prologix + SCPI builders, isolated), `README.md`. |
| `src/drivers/mocks/spreos_power_supply_mock.py` | `SpreosPowerSupplyMock(BaseDriver)`; stateful Qt-free mock for `data/SPREOS Power Supply Main Card Fix.tst`. Tracks `setvoltage`/`setlogic`/`setload` and returns plausible per-channel readings (CH1 PS, CH3/CH4 DAQ taps, CH5 3315G load). Implements the optional `set_active_step(unit, min, max)` hook to tell volts from amps on channels read for both, and to nudge the occasional reading out of spec (`fail_prob`, default 0.02). Passes mostly, fails occasionally. |
| `src/drivers/mocks/run_spreos_mock.py` | Qt-free demo harness (no DB/GUI): parses the SPREOS `.tst`, drives every step through `SpreosPowerSupplyMock`, applies the runner's PASS/FAIL logic, and prints per-step + overall results. `--runs/--seed/--fail-prob/--answer-no`. |

## `src/ui/` — Qt presentation layer

| File Path                              | Short Description                                                                                                                          |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `src/ui/__init__.py`                   | Package marker.                                                                                                                            |
| `src/ui/report_worker.py`              | **(NEW)** `ReportWorker(QThread)`; runs `ReportGenerator.generate_pdf_auto_archive` off the GUI thread; emits `archived(str)` or `failed(str)`. |
| `src/ui/preflight_worker.py`           | **(NEW, Phase 4)** `PreflightWorker(QThread)`; runs `factory.preflight()` off the GUI thread (so a VISA/serial open-timeout never freezes the UI); emits `completed(bool ok, list report)`. Used by the run path and the Connections "Test Connection" button. |
| `src/ui/ui_helpers.py`                 | `attach_password_visibility_toggle()` and an emoji-icon helper, shared by login/user/audit dialogs.                              |
| `src/ui/widgets/__init__.py`           | Package marker.                                                                                                                            |
| `src/ui/widgets/control_panel.py`      | **(CHANGED)** `ControlPanelWidget`; start/stop, save-log checkbox, user box (detachable via `take_user_box`), unit fields, status group, loop count, stop-on-fail, **`chk_simulation` (Simulation mode, default on)**. Emits `start_requested`/`stop_requested` signals; exposes `set_running_state(bool)`. Pass/fail labels use objectName QSS selectors (Rule 4 compliant). |
| `src/ui/widgets/instrument_panel.py`   | **(NEW)** `InstrumentPanelWidget`; live voltage/current readout rows, fed by `MonitorThread`.                                              |
| `src/ui/widgets/result_row_delegate.py`| **(NEW)** `ResultRowDelegate`; paints PASS/FAIL cell tints in the results table.                                                          |
| `src/ui/views/__init__.py`             | Package marker.                                                                                                                            |
| `src/ui/views/main_window.py`          | **(CHANGED)** `MainWindow`; ribbon, menu bar, role gating, pre-test flow, live monitor wiring, trace log, results table, report export, audit logging, and runner wiring. Uses `ControlPanelWidget.start_requested`/`stop_requested` intent signals and `set_running_state()`. Per-run driver selection: Simulation → `build_bench()` launches immediately; Hardware → `PreflightWorker` (async, Start disabled) then `_on_preflight_completed` starts the run or shows a `QMessageBox` offering fallback to Simulation/abort. `_launch_runner()` builds `TestRunnerThread` with the resolved driver. |
| ~~`src/ui/views/main_window.ui`~~      | **DELETED (2026-06-07)** — was STALE/UNUSED. Qt Designer file; UI is built entirely in Python; `loadUi`/`QUiLoader` appeared nowhere. |
| `src/ui/views/login_dialog.py`         | **(CHANGED)** `LoginDialog`; authenticates via `AuthManager`, writes a "User Logged In" audit row. Loads `style.qss` directly. No password-change flow. |
| `src/ui/views/pre_test_dialog.py`      | **(NEW)** `PreTestDialog`; collects UUT type / serial / tester name before a run.                                                          |
| `src/ui/views/select_test_dialog.py`   | **(NEW)** `SelectTestDialog`; pick a version from the DB catalog; writes its content to a temp `.tst` for execution.                       |
| ~~`src/ui/views/sequence_editor_dialog.py`~~ | **DELETED** — retired; step reorder/add/remove now lives only in the raw `.tst` editor + Version Manager import. |
| `src/ui/views/script_editor.py`        | `ScriptEditorDialog`; raw `.tst` text editor. **Only used by the Version Manager** (`_edit`), not from the main ribbon.                    |
| `src/ui/views/test_result_dialog.py`   | **(NEW)** `TestResultDialog`; full-screen PASS/FAIL banner shown at end of run for **all** roles. Inline-styled.                           |
| `src/ui/views/user_management_dialog.py`| `UserManagementDialog` + `UserEditDialog`; Admin CRUD over users/roles. Does **not** call `validate_password_strength`.                   |
| `src/ui/views/version_manager_dialog.py`| **(CHANGED)** `VersionManagerDialog` + `ImportTestMetaDialog`; Admin import/view/edit/delete/export of test versions. 4-col table (Product Name, UUT Type, Version, Date). |
| `src/ui/views/limits_editor_dialog.py` | **(NEW)** `LimitsEditorDialog`; Admin-only step-parameter editor for the loaded test. One row per step; fixed columns: Test (r/o), Value, Low, High, Unit, Channel (`readchannel` arg), Crit (checkbox). Value = the step's numeric setpoint when present, else the on/off state of a `relay`/`setlogic` command. `PromptYesNo` has no stored value (runtime answer) so it shows "—". Delay, Retry, and Prompt text are out of scope. Multi-command steps are supported — only the identified Value/Channel args and step-level fields are written back; all other command lines are preserved on serialize. Opens capped to the screen so buttons stay visible; maximizable via the title bar or a Maximize button. Apply writes a temp `.tst`; Save creates a new DB version. Works on a deep copy of `ScriptDocument.steps` — live document never mutated. |
| `src/ui/views/connections_dialog.py`  | **(CHANGED, Phase 0/4)** `ConnectionsDialog`; Admin-only. One `QLineEdit` per `INSTRUMENTS` ∪ `BENCH_INSTRUMENT_NAMES` entry (serial / VISA / Prologix formats), plus a global **Bench wiring** group (`daq_relay_channel`, `load_slot`, `daq_channel_map`) persisted to `bench_config`. Save upserts + logs audit. A **Test Connection** button runs `PreflightWorker` on the *current* field values (background; result in a `QMessageBox`). |
| `src/ui/views/audit_viewer_dialog.py`  | **(CHANGED)** `AuditViewerDialog`; Admin viewer for DB audit rows and decrypted daily `sys_*.dat` hardware logs (password-gated export). Window title: "Logs".       |
| `src/ui/views/connection_settings_form.py`| **(NEW)** `ConnectionSettingsForm`; edits a `PORT\|BAUD\|PARITY\|STOP_BITS` string; enumerates COM ports via `pyserial` when available.   |
| `src/ui/assets/light_theme.qss`        | Light QSS theme (applied at the `QMainWindow` root).                                                                                       |
| `src/ui/assets/dark_theme.qss`         | Dark QSS theme (applied at the `QMainWindow` root).                                                                                        |
| `src/ui/assets/style.qss`              | **(CHANGED)** Login-screen stylesheet. Contrary to the previous manifest, it **is** loaded — by `LoginDialog`.                            |
| `src/ui/assets/icons/`                 | App icon, brand logo, and theme/ribbon SVG/PNG icons (`BirdAppIcon.png`, `BirdLogo.png`, `moon.svg`, `sun.svg`, `logout.svg`, `power.svg`, …). |

## `src/data/` — seed config & writable state

| File Path                       | Kind          | Short Description                                                                                              |
| ------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------- |
| `src/data/sequence.tst`         | config (seed) | Default sequence loaded on launch for non-operator roles.                                                     |
| `src/data/demo_system.tst`      | config (seed) | Demo script exercising every keyword/command.                                                                 |
| `src/data/28VDC Power Supply Input.tst`           | config | Real-world sample sequence.                                                                          |
| `src/data/SPREOS Power Supply Main Card.tst`      | config | Real-world sample sequence.                                                                          |
| `src/data/12VDC RF Module Stabilized Output Interface.tst` | config | Real-world sample sequence.                                                                 |
| `src/data/limits.json`          | config        | **(STALE/UNUSED)** Legacy JSON limits. Keys do not match any current `.tst` test names. Still seeded by `paths.py` and bundled by the spec. |
| `src/data/database.db`          | state         | SQLite DB (runs, results, users, versions, audit). Created on first run; git-ignored.                          |
| `src/data/logs/`                | state         | Encrypted daily hardware/system logs (`sys_YYYYMMDD.dat`); git-ignored.                                        |
| `src/data/results/`             | state         | Auto-archived PDF reports under `<UUT>/<Serial>/`; git-ignored.                                                 |
| ~~`src/data/secure_system.log`~~ | state        | **DELETED (2026-06-07)** — was STALE. Older plaintext log artifact superseded by `logs/sys_*.dat`. |
| `src/data/tmp/`                 | state         | App scratch directory; created on startup and swept clean by `_sweep_tmp()` in `main.py`. Temp `.tst` files from `SelectTestDialog` land here instead of the OS `%TEMP%`. |

## Build & tooling

| File Path             | Short Description                                                                                                  |
| --------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `requirements.txt`    | Six runtime deps: `PySide6`, `reportlab`, `PyPDF2`, `cryptography`, `pyserial`, `python-dotenv`.                   |
| `DFX_Tester.spec`     | **(NEW)** PyInstaller onedir spec. Bundles assets + seed data; force-includes `cryptography`. **Excludes `serial`** even though `connection_settings_form.py` imports it (falls back to a static port list — see audit). |
| `build.ps1`           | **(NEW)** PowerShell build driver: installs deps + PyInstaller, cleans, runs the spec, prints the bundle path.    |
| `.pylintrc`           | Pylint config; whitelists PySide6 C-extensions.                                                                   |
| `.gitignore`          | Ignores build output, venvs, `*.db`/`*.lock`/`*.log`, `src/data/results/`, `*.csv/*.json/*.txt`, and `*PLAN*.md`. |

## Documentation (`DOC/`)

| File Path                       | Short Description                                                                  |
| ------------------------------- | --------------------------------------------------------------------------------- |
| `DOC/.env.example`              | Template with every supported `.env` key, dummy/safe values, and usage comments. Copy to `.env` next to the EXE (or repo root). **Do not commit `.env`**. |
| `DOC/FILE_MANIFEST.md`          | This file.                                                                         |
| `DOC/ARCHITECTURE_DEEP_DIVE.md` | Threading, data strategy, subsystems, signal map, schema, boot flow, RBAC.        |
| `DOC/SPECIFICATIONS.md`         | Pinned environment, dependencies, deployment.                                     |
| `DOC/TECH_STACK.md`             | Required engineering competencies.                                                |
| `DOC/DEVELOPMENT_RULES.md`      | Architectural guardrails (with current-reality notes).                            |
| `DOC/KEYWORDS_DICTIONARY.md`    | `.tst` script language reference.                                                 |
| `README.md`                     | Top-level project overview (note: still uses the old role name "Engineer").       |
| `PROJECT_CONTEXT.md`            | **(NEW)** Condensed team reference: what the project is, folder map, RBAC table, DB schema, .tst language, threading model, .env keys, architectural rules, and Q&A hooks. Intended to be loaded as context into Claude web for team Q&A. |

## Files referenced by old docs that do NOT exist

- `src/ui/views/change_password_dialog.py` — never present in the tree; there is no
  password-change dialog and no `must_change_pwd` flow anywhere in the code.
