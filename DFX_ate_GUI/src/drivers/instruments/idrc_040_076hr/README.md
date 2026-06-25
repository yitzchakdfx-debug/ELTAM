# IDRC-040-076HR driver (programmable DC power supply)

Main bench supply for the SPREOS test (CH1). Sets the input voltage and reads
back its output voltage/current.

| | |
|---|---|
| **Capabilities** | `VoltageSource` (set_output/set_voltage/measure_voltage/measure_current) + `set_protection(ovp, ocp)` |
| **Transport** | RS-232 (pyserial) |
| **Identity** | `*IDN?` *(provisional — see below)* |
| **Files** | `driver.py` (real), `mock.py` (sim), `protocol.py` (command builders) |

## ⚠ Protocol is PROVISIONAL

The command set in `protocol.py` (`VOLT`, `OUTP ON|OFF`, `MEAS:VOLT?`,
`MEAS:CURR?`, `VOLT:PROT`, `CURR:PROT`, `*IDN?`) is an **assumed conventional
SCPI dialect** and is **not yet confirmed against the IDRC programming manual**.
Confirm before connecting to hardware:

- exact command verbs and whether the unit uses SCPI or a proprietary framing,
- line termination (`\n` / `\r\n` / `\r`) and whether it echoes,
- whether `*IDN?` is supported or a custom identity command is required,
- settle time after `set_voltage` and whether a readback verify is needed.

All framing lives in `protocol.py`, so confirming the manual is a one-file change.

## Connection (canonical: `instrument_connections`)

The address/serial params come **only** from the `instrument_connections` table
(canonical; `test_versions.connection_params` is legacy and not used for routing).
The factory decodes the stored `PORT|BAUD|PARITY|STOP` string into
`ConnInfo(transport="serial", resource="COM4", params={"baud":…, "parity":…, …})`
and calls `open()`. Defaults: 9600 N-8-1, 2 s timeout, no RTS/CTS *(confirm)*.

`is_available()` returns `True` iff pyserial imports; the specific COM port is
validated at `open()`.

## Safety

`close()` drives `OUTP OFF` before releasing the port (also on abort). The SPREOS
INIT step sets `OVP=35 V, OCP=20 A` — call `set_protection(35, 20)` on connect.

## Provenance / TODO(bench)

- No vendor DLL (pure serial), so nothing is copied into `drivers/vendor/`.
- TODO(bench): confirm baud/parity/termination and the real `*IDN?` string on the
  unit; add a post-`set_voltage` readback verify if the supply needs settle time.
