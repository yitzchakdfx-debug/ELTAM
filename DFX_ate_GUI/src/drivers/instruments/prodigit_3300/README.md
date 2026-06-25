# Prodigit 3300G driver (mainframe + 3315G electronic load)

Electronic load for the SPREOS test (CH5). Applies a constant-power load and reads
back load voltage/current.

| | |
|---|---|
| **Capabilities** | `ElectronicLoad` (set_mode/set_power/set_input/measure_voltage/measure_current) |
| **Transport** | **Prologix GPIB-USB** adapter over RS-232/USB (reuses `SerialSession`) |
| **Identity** | `NAME?` (Prodigit family — returns the module name; `"NULL"` = empty slot) |
| **Files** | `driver.py` (real), `mock.py` (sim), `protocol.py` (Prologix + SCPI builders) |

## Architecture: one mainframe, four slots

The 3300G mainframe has **one GPIB address** and holds up to **4 load modules**
(e.g. the 3315G). The driver targets one slot:

```python
Prodigit3300Load(load_slot=<1..4>, gpib_address=<0..30>)
```

`load_slot` is the global `bench_config.load_slot`; `gpib_address` comes from the
canonical `instrument_connections` entry (the COM port of the Prologix bridge is
the `ConnInfo.resource`).

## Prologix addressing + channel routing (both isolated in `protocol.py`)

On `open()` the driver sends, over the serial line to the adapter:

```
++mode 1          # adapter = controller
++addr <gpib>     # target the mainframe
++auto 1          # auto read-after-write (queries return the reply)
```

Then **every** operation selects the slot before the command:

| Operation | Sequence |
|---|---|
| set constant power | `CHAN <slot>` → `MODE CP` then `CHAN <slot>` → `POW <w>` |
| input on / off | `CHAN <slot>` → `LOAD ON` / `LOAD OFF` |
| measure V / I | `CHAN <slot>` → `MEAS:VOLT?` / `MEAS:CURR?` |
| identify / slot probe | `CHAN <slot>` → `NAME?` |

> **3300G vs 3300F:** the G-series uses `MODE CP` + `POW <w>` (this driver). The
> older 3300F family used `CP:HIGH`/`CP:LOW` — do not mix them up.

## Safety

`close()` (and abort) drives `LOAD OFF` before releasing the port. `identify()`
treats an empty/`"NULL"` slot as a failure, so a mis-set `load_slot` surfaces at
the bench comms-check instead of silently mis-testing.

## Provenance / TODO(bench)

- Command set confirmed from the 3300G mainframe manual (per project review).
- TODO(bench): confirm `NAME?` is the G-series identity command and the `"NULL"`
  empty-slot reply; confirm the Prologix serial params (baud is nominal over
  USB-CDC) and response termination; add the 3315G power-band safety clamp once
  the datasheet boundaries are known.
- No vendor DLL (Prologix is a serial device), so nothing is copied into
  `drivers/vendor/`.
