# KEYWORDS DICTIONARY - The `.tst` Script Vocabulary

The complete reference for the script language consumed by
[`ScriptManager.load_script`](../src/logic/script_manager.py) and executed by
[`TestRunnerThread`](../src/logic/test_engine.py).

## General syntax rules

- One statement per line. Trailing whitespace is ignored.
- Comments start with `#` and run to end of line. Inline comments are allowed.
- Blank lines and lines before the first `:` header are ignored (file preamble).
- **Keyword names are case-insensitive** (`Critical` == `CRITICAL` == `critical`).
- Test names (everything after the `:`), unit strings, and command arguments
  preserve their original case.
- `Limits` and `Tolerance` (`Target ... Tol ...`) are **mutually exclusive** within
  a single step.

## Header keywords (script preamble)

Header keywords are parsed before the first `:<Test Name>` block and are used as
metadata that can drive the UI.

| Keyword | Syntax | Description |
| --- | --- | --- |
| `PartNum` | `PartNum: <value>` (or `# PartNum: <value>`) | Sets the default part number for the loaded script. The UI auto-populates the part-number field if the operator has not manually edited it. |

## Core Structural Keywords

| Keyword     | Syntax                       | Description                                                                                                  |
| ----------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `:`         | `:<Name>`                    | **Test Header**: Starts a new test block.                                                                    |
| `Critical`  | `Critical`                   | **Abort on Fail**: Stops the entire sequence if this step fails.                                             |
| `Limits`    | `Limits <min> <max>`         | **Fixed Range**: Sets the PASS/FAIL boundaries.                                                              |
| `Tolerance` | `Target <val> Tol <%>`       | **Dynamic Range**: Calculates limits from a target and a percentage (e.g. `Target 5.0 Tol 10`).             |
| `Unit`      | `Unit <str>`                 | **Units**: Sets the unit string for reporting (`V`, `A`, etc.).                                              |
| `Delay`     | `Delay <ms>`                 | **Wait**: Pauses execution for X milliseconds.                                                               |
| `Retry`     | `Retry <num>`                | **Auto-Repeat**: Re-runs the step up to X times if it fails before declaring a final FAIL.                   |
| `Prompt`    | `Prompt <msg>`               | **User Action**: Pauses and shows a popup message. Waits for user "OK" to continue.                          |
| `Log`       | `Log <msg>`                  | **Trace Note**: Prints a custom message directly to the Hardware Trace log.                                  |

`Critical`, `Limits`, `Tolerance`, `Unit`, and `Retry` are step-level
configuration: they apply to the most recent `:` header. `Delay`, `Prompt`,
and `Log` are *per-line commands* and may appear anywhere inside a step, in
sequence with hardware commands.

## Hardware commands (mock backend)

The set of hardware commands recognized by `MockHardware.execute_command`:

| Command       | Kind          | Syntax                       | Notes                                                                                          |
| ------------- | ------------- | ---------------------------- | ---------------------------------------------------------------------------------------------- |
| `setvoltage`  | side-effect   | `setvoltage <volts>`         | Sets a rail to the requested voltage. Returns no measurement.                                  |
| `relay`       | side-effect   | `relay <id> <on\|off>`       | Switches a relay. Returns no measurement.                                                      |
| `setlogic`    | side-effect   | `setlogic <line> <on\|off>`  | Drives a logic/digital output line; applies voltage to switch a device on or off. `<line>` is an integer id; `<on\|off>` is text only, case-insensitive (like `Yes\|No` for `PromptYesNo`). Returns no measurement. The `BenchDriver` routes this to the DAQ-9600 `DiscreteIO` capability — `set_line(bench_config.daq_relay_channel, state)` — so the physical relay channel is dynamic config, not code (*the channel number still needs the bench wiring diagram*). |
| `getid`       | side-effect   | `getid`                      | Mock identification ping. Returns no measurement.                                              |
| `setload`     | side-effect   | `setload <watts>`            | Sets an electronic load (e.g. 3315G) to a constant-power setpoint in watts; `setload 0` clears it. **Not implemented by the generic `MockHardware`** — only by test-specific mocks (see below). Returns no measurement. |
| `readchannel` | measurement   | `readchannel <channel>`      | Reads channel `<channel>`. The **last** measurement value executed in a step is what gets compared against `Limits` / `Tolerance`. A driver sees only the channel number, so when one channel is read for two quantities (e.g. volts then amps), the driver must use the step's `Unit` to tell them apart — see the context hook below. On the SPREOS bench the `BenchDriver` maps the logical channel to an instrument role (PS/load/DAQ) and, for DAQ taps, remaps it to the physical mux channel via `bench_config.daq_channel_map`. |

The set of measurement commands is defined by the driver's
`measurement_commands` property (a `frozenset[str]`, currently `{"readchannel"}`
for `MockHardware`). Adding a new measurement command means appending it to
that frozenset, implementing it in the driver's `execute_command`, and adding a
row here. `setlogic` is a side-effect command and is **not** in
`measurement_commands`.

Any unknown command name raises
`drivers.base_driver.UnknownCommandError("Unknown hardware command: ...")`
inside the runner; the step is marked FAIL and the trace shows the offending
command. (So a script using `setload` against the generic `MockHardware` will
FAIL that step — run it against a mock that implements `setload`, e.g.
`SpreosPowerSupplyMock`.)

### Driver context hook (optional)

Before running a step's commands, `TestRunnerThread` calls
`driver.set_active_step(unit, min_val, max_val)` **if the driver defines it**.
`MockHardware` does not, so this is a no-op there. Test-specific mocks under
`src/drivers/mocks/` use it to (a) decide whether a channel reused for two
quantities is being read for volts or amps, and (b) know the limit window so
they can occasionally return an out-of-spec value. See
`DOC/FILE_MANIFEST.md` → `src/drivers/mocks/`.

## Worked example

```text
# Power-up a UUT, prompt the operator, take a tolerance-checked measurement,
# and retry it once if the supply has not settled.

:Power Supply Init
Critical
setvoltage 5.0
Delay 200

:Operator Confirm
Prompt Insert UUT and click OK to continue
Log Operator confirmed UUT insertion

:5V Output Voltage
Target 5.0 Tol 5
Unit V
Retry 1
readchannel 0

:Cleanup
setvoltage 0.0
```

Behavior:

1. `Power Supply Init` is critical: any failure aborts the run.
2. `Operator Confirm` parks the runner on `Prompt`; the GUI shows a
   `QMessageBox` and the runner only continues after the operator clicks
   OK. The `Log` line then appears in the Hardware Trace in a distinct
   style.
3. `5V Output Voltage` derives its limits from `Target 5.0 Tol 5` (i.e.
   min 4.75, max 5.25). If `readchannel 0` returns out-of-range, the
   runner re-runs the step once before declaring a final FAIL.
4. `Cleanup` runs unconditionally as a non-measured pass row.

## Validation summary

The parser raises a `ScriptParseError(line_no, line, msg)` for any of:

- A `:` header with an empty name.
- A keyword (`Critical`, `Limits`, `Tolerance`, `Unit`, `Retry`) appearing
  before any `:` header.
- A command appearing before any `:` header.
- `Critical` with extra arguments.
- `Limits` without exactly two numeric arguments, or with `min > max`.
- `Target ... Tol ...` with the wrong shape, with non-numeric `<val>` /
  `<pct>`, with `<pct>` negative, or when the step already has `Limits`.
- `Limits` when the step already has `Target/Tol`.
- `Unit` without a unit string.
- `Retry` without exactly one non-negative integer argument.

`TestRunnerThread` catches `ScriptParseError` and emits the error to the
trace log; it does not throw out of the QThread.
