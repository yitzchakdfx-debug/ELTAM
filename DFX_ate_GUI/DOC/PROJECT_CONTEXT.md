# DFX_ate — Project Context Reference

> Paste this file into Claude web as context. It covers what the project is,
> where everything lives, and how the key systems work.
> Last synced: 2026-06-07.

---

## What this project is

**DFX_ate** is a Windows desktop ATE (Automated Test Equipment) front-end built
with PySide6. It runs keyword-driven `.tst` test scripts against hardware
(currently the `SpreosPowerSupplyMock` stand-in, injected by `MainWindow`; real
drivers slot in via `BaseDriver` at that same swap point), records results
in SQLite, generates PDF/CSV reports, and provides role-gated access for factory
floor operators.

- Entry point: `src/main.py`
- All source lives under `src/`
- Config is in `.env` at the repo root (git-ignored); `src/env.py` loads it
- Secrets/flags are never hardcoded — always in `.env` → `src/config.py`

---

## Tech stack

| Concern | Library / tool |
|---|---|
| UI | PySide6 (Qt6) |
| DB | SQLite via stdlib `sqlite3` |
| PDF | ReportLab + PyPDF2 |
| Encryption | `cryptography` (Fernet / PBKDF2) |
| COM ports | `pyserial` (optional; graceful fallback) |
| Config | `python-dotenv` |
| Build | PyInstaller onedir (`DFX_Tester.spec`) |
| Python | 3.11+ |

---

## Folder map

```
src/
  main.py              # entry point: lock → login loop → MainWindow
  env.py               # .env loader (load_env_once, get_str/bool/list)
  config.py            # all app constants — reads from env.py
  paths.py             # resource_path / user_data_path / user_tmp_path
  version.py           # __version__ from .env APP_VERSION

  logic/               # Qt-free business logic (+ 2 sanctioned QThreads)
    test_engine.py     # TestRunnerThread — runs .tst sequences
    script_manager.py  # ScriptManager — parse/read/write .tst files
    database_manager.py# DatabaseManager — thin facade over logic/db/
    db/                # SQL repository sub-package
      connection.py    # open_conn() factory
      schema.py        # CREATE TABLE + migrations + admin seed
      users.py         # user CRUD + verify_login
      test_versions.py # version catalog CRUD
      audit.py         # audit log write + read
      test_runs.py     # save_run (test_runs + test_results)
    auth_manager.py    # AuthManager — thin wrapper over DatabaseManager
    models.py          # TestStep, ScriptDocument, TestRunRecord, normalize_role()
    report_generator.py# ReportGenerator — PDF + CSV, role-gated detail
    secure_logger.py   # SecureLogger — Fernet-encrypted daily .dat logs
    monitor_engine.py  # MonitorThread — emits simulated V/A readings
    file_lock.py       # SingleInstanceLock (Windows: named mutex)

  drivers/
    base_driver.py     # BaseDriver (ABC) + identify() default + HardwareError hierarchy
    mock_hardware.py   # MockHardware(BaseDriver) — generic Qt-free simulator
    mocks/             # test-specific stateful mocks (SpreosPowerSupplyMock)
    bench/             # BenchDriver (command router) + instrument_base + command_map + sim_bus + factory.build_bench()
    instruments/       # per-device drivers: daq_9600, idrc_040_076hr, prodigit_3300 (real + mock + protocol each)

  ui/
    report_worker.py   # ReportWorker(QThread) — PDF build off GUI thread
    ui_helpers.py      # attach_password_visibility_toggle + icon helper
    widgets/
      control_panel.py # ControlPanelWidget — start/stop/status/loops rail
      instrument_panel.py  # InstrumentPanelWidget — live V/A readout
      result_row_delegate.py # PASS/FAIL cell tints
    views/
      main_window.py       # MainWindow — composition root (~1,200 lines)
      login_dialog.py      # LoginDialog
      pre_test_dialog.py   # UUT type / serial / tester name before run
      select_test_dialog.py# Operator picks from DB version catalog
      sequence_editor_dialog.py # Reorder/add/remove steps, save version
      script_editor.py     # Raw .tst text editor
      version_manager_dialog.py # Admin: import/view/edit/delete versions
      audit_viewer_dialog.py    # Admin: DB audit rows + decrypt .dat logs
      user_management_dialog.py # Admin: CRUD users/roles
      test_result_dialog.py     # Big PASS/FAIL banner at end of run
      connection_settings_form.py # PORT|BAUD|PARITY|STOP_BITS editor
    assets/
      light_theme.qss / dark_theme.qss  # full app QSS themes
      style.qss                         # login screen only

  data/                # writable state (git-ignored)
    database.db        # SQLite
    logs/              # encrypted sys_YYYYMMDD.dat files
    results/           # archived PDFs under <UUT>/<Serial>/
    tmp/               # scratch .tst files, swept on startup
```

---

## Roles (RBAC)

Three roles — **Operator / Technician / Admin** (stored in DB `CHECK` constraint).

| Feature | Operator | Technician | Admin |
|---|---|---|---|
| Run tests | ✓ | ✓ | ✓ |
| See Min/Max in UI | ✗ | ✗ | ✓ |
| Trace log | ✗ | ✓ | ✓ |
| Sequence Editor | ✗ | ✓ | ✓ |
| Select Test (from catalog) | ✓ only | optional | ✓ |
| Save PDF report | ✗ | ✗ | ✓ |
| Versions manager | ✗ | ✗ | ✓ |
| Audit viewer | ✗ | ✗ | ✓ |
| User management | ✗ | ✗ | ✓ |

DB stores full Min/Max always — gating is visual only.

---

## Database schema (5 tables)

```
test_runs       id, operator, part_number, serial_number,
                overall_passed, start_time, end_time

test_results    id, run_id FK→test_runs, test_name, value,
                min_val, max_val, unit, passed

users           id, username (UNIQUE NOCASE), password_hash, salt,
                role CHECK(Operator/Technician/Admin),
                employee_id, created_at, updated_at

test_versions   id, test_name, uut_type, version_name, test_content,
                connection_params (PORT|BAUD|PARITY|STOP_BITS),
                created_at, created_by
                UNIQUE(test_name, version_name)

audit_logs      id, timestamp, username, employee_id, action, details
```

- Passwords: PBKDF2-HMAC-SHA256, 200k iterations, 16-byte random salt per user
- All queries parameterized — zero string-interpolated SQL
- `DatabaseManager._schema_ready` class flag: DDL runs once per process

---

## .tst script language (key syntax)

```
# comment
PartNum: ABC-123      # fills UI part-number field

: Step Name           # opens a new step
Critical              # abort whole run if this step fails finally
Limits 4.5 5.5        # pass if last measurement in [4.5, 5.5]
Target 5.0 Tol 10     # equivalent: Limits 4.5 5.5 (resolved at parse)
Unit V
Retry 2               # run up to 3 times; report only final attempt

readchannel 1         # hardware command → MockHardware.execute_command
Delay 500             # runner-side sleep, never reaches hardware
Log "message"         # emit trace line
Prompt "operator msg" # park runner until operator clicks OK
```

`ScriptManager.validate_version_name(name)` — call before saving a version name.

---

## Threading model

```
GUI thread          MainWindow (PySide6 event loop)
Worker thread 1     TestRunnerThread  — runs the .tst sequence
Worker thread 2     MonitorThread     — emits V/A every 500 ms
Short-lived         ReportWorker      — builds PDF after a run
```

- Cross-thread: Qt signals (auto QueuedConnection)
- Cancel: cooperative boolean flag + `threading.Event` (wakes prompt/pause)
- Pause: `_pause_event` cleared = paused; set = running (checked at step boundaries)
- Shutdown: `MainWindow._shutdown_threads()` — called from both `closeEvent` and `logout`

---

## Key signals (TestRunnerThread → MainWindow)

`log_msg(str)`, `test_result(str, dict)`, `loop_started(int, int)`,
`progress_total(int)`, `progress_test(int)`, `current_test(str)`,
`prompt_request(str)`, `script_log(str)`, `finished` (built-in)

---

## .env keys

```
LOG_ENCRYPTION_PASSWORD   # Fernet key source for daily .dat logs
ADMIN_REPORT_PASSWORD     # PDF encryption password for Admin reports
DEFAULT_ADMIN_USERNAME    # seeded only on first DB creation
DEFAULT_ADMIN_PASSWORD    # seeded only on first DB creation
DEFAULT_ADMIN_EMPLOYEE_ID
APP_VERSION               # shown in window title
TESTER_SERIAL_NUMBER      # printed on reports
SHOW_LIVE_MONITOR         # true/false
SHOW_SEARCH_BAR           # true/false
UUT_TYPES                 # comma-separated list for PreTest combo
```

---

## Architectural rules (short form)

1. **No UI in logic** — `logic/` and `drivers/` never import `QtWidgets`/`QtGui`
2. **No blocking on GUI thread** — hardware, sleep, PDF → worker threads
3. **No secrets in source** — everything in `.env`
4. **All SQL in `logic/db/`** — no `sqlite3` imports anywhere else
5. **No inline styles** — use objectName + `.qss` selectors; never `setStyleSheet("...")`
6. **Roles are Operator / Technician / Admin** — not "Engineer"
7. **Simple passwords are intentional** — factory-floor shared stations; no policy enforcement

---

## Common Q&A hooks

- **Where are reports saved?** `data/results/<UUT_type>/<Serial_number>/`
- **Where are encrypted logs?** `data/logs/sys_YYYYMMDD.dat`
- **Where is the DB?** `data/database.db` (next to the EXE in prod)
- **How to add a new test step type?** Add keyword to `ScriptManager.load_document` parser + `KEYWORDS_DICTIONARY.md`
- **How to add a real hardware driver?** Subclass `BaseDriver`, implement `connect/disconnect/execute_command/measurement_commands`; pass instance to `TestRunnerThread(driver=...)`
- **How to add a new .env key?** Add to `config.py` via `env.get_str/bool/list`, add to `DOC/.env.example`
- **Password hashing algo?** PBKDF2-HMAC-SHA256, 200k iterations, 16-byte salt, stored as BLOB
- **Single instance enforcement?** Named Windows mutex `Local\DFX_ate_singleton` via `ctypes`
