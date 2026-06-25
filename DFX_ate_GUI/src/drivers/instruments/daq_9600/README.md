# DAQ-9600 driver (GW Instek DAQ-9600 + DAQ-901 multiplexer)

DVM / scanner for the SPREOS bench. Reads DC voltage on multiplexed channels
(CH3 = JX1, CH4 = JX2-4 in the SPREOS test) and drives the `setlogic` relay via a
switch channel.

| | |
|---|---|
| **Capabilities** | `Multimeter` (configure/read), `DiscreteIO` (set_line/get_line) |
| **Transport** | VISA (pyvisa) — USB / LAN / GPIB resource string |
| **Identity** | standard SCPI `*IDN?` |
| **Files** | `driver.py` (real), `mock.py` (sim), `protocol.py` (SCPI builders) |

## Connection (canonical: `instrument_connections`)

At runtime the address comes **only** from the `instrument_connections` table
(the canonical source of truth; `test_versions.connection_params` is legacy and
not used for hardware routing). The factory decodes the stored string into a
`ConnInfo(transport="visa", resource="<VISA string>")` and calls `open()`.

VISA resource examples:
- USB: `USB0::0x2A8D::0x...::<serial>::INSTR`
- LAN: `TCPIP0::192.168.0.50::INSTR`
- GPIB: `GPIB0::9::INSTR`

`is_available()` returns `True` only if `pyvisa` imports **and** a VISA backend
(NI-VISA or `pyvisa-py`) opens a `ResourceManager`. With no backend the bench
preflight keeps the station in Simulation and names this instrument.

## Channel addressing

Channels use the GW/Keysight `(@sccc)` form (slot + channel), e.g. the DAQ-901 in
slot 1 → `101..120`, rendered `(@101)`. The mapping from a script's logical
`readchannel N` to a physical channel is **not** in this driver — it lives in the
per-version channel map (Phase 3). The `setlogic` relay channel is the global
`bench_config.daq_relay_channel` (pending the bench wiring diagram).

## Command reference (see `protocol.py`)

| Purpose | SCPI |
|---|---|
| Identify | `*IDN?` |
| Configure DC volts | `CONF:VOLT:DC (@<ch>)` |
| Measure | `MEAS:VOLT:DC? (@<ch>)` |
| Close relay (line ON) | `ROUT:CLOS (@<ch>)` |
| Open relay (line OFF) | `ROUT:OPEN (@<ch>)` |
| Relay state | `ROUT:CLOS? (@<ch>)` |

## Provenance / TODO(bench)

- SCPI verified against the DAQ-9600 programming manual (Keysight 349xx-compatible
  set). Confirm the exact `*IDN?` vendor string and DAQ-901 channel numbering on
  the bench.
- `read()` measures with `MEAS:<func>? (@ch)` (configure remembers the function).
  If scan throughput matters later, switch to `CONF` + `ROUT:SCAN` + `READ?`.
- No vendor DLL required (pure VISA), so nothing is copied into `drivers/vendor/`.
