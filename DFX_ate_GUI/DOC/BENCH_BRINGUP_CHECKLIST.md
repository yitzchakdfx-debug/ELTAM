# BENCH BRING-UP CHECKLIST — SPREOS Power Supply Main Card

A practical, step-by-step field guide for the integration engineer taking
DFX_ate to the lab to connect the **real** SPREOS bench for the first time.

**Bench (3 instruments):**

| Role | Device | Link | Driver |
| --- | --- | --- | --- |
| Power Supply | IDRC-040-076HR | RS-232 (USB-serial) | [`idrc_040_076hr/`](../src/drivers/instruments/idrc_040_076hr/) |
| DVM / MUX | GW Instek DAQ-9600 + DAQ-901 | VISA (USB or LAN) | [`daq_9600/`](../src/drivers/instruments/daq_9600/) |
| Electronic Load | Prodigit 3300G + 3315G module | **Prologix GPIB-USB** (serial) | [`prodigit_3300/`](../src/drivers/instruments/prodigit_3300/) |

> Golden rule: **the UI Connection Settings dictate the hardware reality.** No COM
> port, GPIB address, slot, or DAQ channel is hardcoded — everything below is
> entered in the dialogs and read fresh at run start.

---

## 0. Host prerequisites (do once per station)

- [ ] Python deps installed: `pip install -r requirements.txt` (includes `pyvisa`, `pyserial`).
- [ ] **VISA backend** for the DAQ-9600 — one of:
  - **NI-VISA** (recommended; required if you ever drive GPIB through an NI adapter), or
  - **pyvisa-py** (`pip install pyvisa-py`) — pure-Python, fine for USB/LAN VISA, **no GPIB**.
- [ ] **USB-serial drivers** present so the OS enumerates the COM ports:
  - the IDRC's RS-232↔USB adapter, and
  - the **Prologix GPIB-USB** adapter (shows up as a COM port — note it in Device Manager).
- [ ] Sanity check in **Simulation mode** first: launch the app, run the SPREOS test
  with "Simulation mode" checked — it should complete (mostly PASS). This confirms
  the software is healthy before any hardware is involved.

---

## 1. Physical setup — verify before touching the UI

- [ ] **IDRC Power Supply** — connect RS-232/USB; note the **COM port** (e.g. `COM3`)
      and the supply's serial settings (baud/parity) from its front panel/manual.
- [ ] **DAQ-9600** — connect USB or LAN; obtain its **VISA resource string**
      (NI MAX, or `python -c "import pyvisa; print(pyvisa.ResourceManager().list_resources())"`).
      Record:
  - [ ] the DAQ-901 mux channel wired to **JX1** (→ script CH3),
  - [ ] the DAQ-901 mux channel wired to **JX2-4** (→ script CH4),
  - [ ] the DAQ switch channel wired to the **logic-power relay** (for `setlogic`).
- [ ] **Prodigit load** — seat the **3315G** module; note its **slot (1-4)**.
      Set the **mainframe GPIB address** on the front panel (e.g. `6`).
      Connect the **Prologix** adapter; note its **COM port** (e.g. `COM5`).
- [ ] Power on all three instruments; confirm they are idle/safe (PS output off,
      load input off).

---

## 2. UI configuration

Open **Admin → Connections** (Admin role required).

### 2a. Per-instrument addresses (canonical: `instrument_connections`)

Fill the field whose label matches **exactly** (names come from
[`bench_spec.py`](../src/drivers/bench/bench_spec.py)):

| Field label | Transport | Format | Example |
| --- | --- | --- | --- |
| **Power Supply** | serial | `PORT\|BAUD\|PARITY\|STOPBITS` | `COM3\|115200\|N\|1` |
| **DAQ-9600** | VISA | raw VISA resource | `TCPIP0::192.168.0.50::INSTR` or `USB0::0x2A8D::…::INSTR` |
| **Electronic Load** | Prologix | `PORT\|BAUD\|PARITY\|STOP\|GPIB:<addr>` | `COM5\|115200\|N\|1\|GPIB:6` |

- [ ] Power Supply COM string entered (baud/parity per the IDRC manual — see §3).
- [ ] DAQ-9600 VISA resource entered.
- [ ] Electronic Load string entered **including `GPIB:<addr>`** (the mainframe's GPIB address).

### 2b. Bench wiring (global: `bench_config`) — the "Bench wiring" group

| Field | Meaning | Example |
| --- | --- | --- |
| **DAQ relay channel** | DAQ-9600 switch channel the `setlogic` relay is wired to | `101` |
| **Load slot (1-4)** | mainframe slot holding the 3315G | `2` |
| **DAQ channel map** | logical script channel = physical DAQ-901 channel | `3=103,4=104` |

- [ ] **Load slot** set (1-4) — *required*; a hardware run won't start without it.
- [ ] **DAQ channel map** set so script `readchannel 3/4` hit the real JX1 / JX2-4 mux channels.
- [ ] **DAQ relay channel** set — *required before running any script that uses `setlogic`*
      (the SPREOS test does). ⚠ See the known gap in §5: this field is **not** checked by
      the preflight, so verify it manually.
- [ ] Click **Save**.

### 2c. Select hardware mode

- [ ] In the right-hand control rail, **uncheck "Simulation mode"**. (Leave it checked to
      keep running against mocks.)

---

## 3. Hardware-in-the-loop validation — `TODO(bench)` to confirm/tweak in code

These are the assumptions baked into the drivers that must be **verified against the
real instruments** and tweaked if wrong. All command strings are isolated in each
instrument's `protocol.py`, so a fix is a one-file change.

### IDRC Power Supply — [`idrc_040_076hr/`](../src/drivers/instruments/idrc_040_076hr/)
- [ ] **Serial params:** confirm baud / parity / stop bits / **line termination**
      (driver default `\n`) and whether the unit **echoes**. Tweak in the Connections
      string and, if needed, `SerialSession` termination in
      [`serial_port.py`](../src/drivers/bench/transports/serial_port.py).
- [ ] **`*IDN?`** returns a sensible identity (SCPI confirmed for the DSP series).
- [ ] **`set_voltage` settling:** verify a readback after `VOLT <v>` matches; if the
      supply needs settle time, the script's existing `Delay` covers it — confirm it's enough.
- [ ] **OVP/OCP (35 V / 20 A):** ⚠ **not programmed automatically.** The SPREOS INIT
      step only *logs* the intent. Either set OVP/OCP on the supply's front panel, **or**
      add `source.set_protection(35, 20)` to `BenchDriver.connect()`
      ([`bench_driver.py`](../src/drivers/bench/bench_driver.py)). Decide and record.

### DAQ-9600 + DAQ-901 — [`daq_9600/`](../src/drivers/instruments/daq_9600/)
- [ ] **`*IDN?`** vendor string is non-empty.
- [ ] **Channel addressing:** `MEAS:VOLT:DC? (@<ch>)` reads the correct tap; confirm the
      DAQ-901 channel numbers used in the **DAQ channel map** (§2b).
- [ ] **`setlogic` relay:** `ROUT:CLOS (@<daq_relay_channel>)` / `ROUT:OPEN` actually
      drives the logic-power relay. Confirm the channel and that CLOS = "logic ON".
- [ ] Reading throughput acceptable with per-read `MEAS?` (if not, switch to
      `CONF` + `ROUT:SCAN` + `READ?` — noted in the driver README).

### Prodigit 3300G / 3315G — [`prodigit_3300/`](../src/drivers/instruments/prodigit_3300/)
- [ ] **Prologix init** works: `++mode 1`, `++addr <gpib>`, `++auto 1` (a query returns a reply).
- [ ] **`NAME?`** returns the module model (the G-series uses `NAME?`, **not** `*IDN?`),
      and an **empty slot replies `"NULL"`** — confirm, since identify() treats `NULL`
      as a failure (catches a mis-set `load_slot`).
- [ ] **Constant power:** `CHAN <slot>` → `MODE CP` → `POW <w>` sets the load; `LOAD ON/OFF`
      enables/disables. Confirm `POW` (G-series) vs the F-series `CP:HIGH/CP:LOW`.
- [ ] **Measurements:** `MEAS:VOLT?` / `MEAS:CURR?` return the right magnitude/format.
- [ ] **Power-band safety clamp:** ⚠ none yet — `set_power` sends `POW <w>` unbounded.
      Once the 3315G datasheet power range / HIGH-LOW boundaries are known, add a clamp
      in `Prodigit3300Load.set_power` / `protocol.set_power`.
- [ ] **Prologix serial params / termination:** baud is nominal over USB-CDC; confirm the
      response termination matches `SerialSession`'s read terminator (`\n`).

### Routing / mapping
- [ ] **Channel map** (`SPREOS_CHANNEL_MAP` in [`command_map.py`](../src/drivers/bench/command_map.py)):
      CH1→PS, CH3/CH4→DAQ, CH5→load. V vs A is chosen from each step's `Unit`.
- [ ] **DAQ logical→physical** remap (`daq_channel_map`, §2b) verified on real reads.

---

## 4. Troubleshooting — isolate faults *before* running a script

### Use **Test Connection** (Admin → Connections)
The **Test Connection** button probes every instrument **using the values currently in
the fields** (it does not save). It runs in the background (UI stays responsive) and
pops a result dialog. Interpret each line:

| Line | Meaning | Fix |
| --- | --- | --- |
| `[OK] <name>: <id>  [transport resource]` | open + identify succeeded | — |
| `[X] <name>: driver/runtime unavailable …` | `is_available()` false — no VISA/serial backend | install NI-VISA / `pyvisa-py` / `pyserial` |
| `[X] <name>: not responding — <error>` | reachable transport but no/garbled reply | powered off, wrong COM/VISA/GPIB, cable, wrong baud |
| `Configuration error: - <item>` | a required field is missing/invalid | fill the field (COM, VISA, `GPIB:<n>`, `load_slot`) |

**Isolate one at a time:** clear two of the three connection fields, **Test**, and bring
each instrument up individually. Then fill all three and Test together.

### Preflight on Run
When you uncheck Simulation and press **Start**, the **same probe** runs automatically
(async — Start disables briefly, the UI never freezes even on a multi-second VISA
timeout). Results stream into the **Hardware Trace**; on any failure a dialog offers to
**fall back to Simulation** or **abort**. Read the trace lines exactly as the table above.

### Common faults
| Symptom | Likely cause | Action |
| --- | --- | --- |
| All three `driver/runtime unavailable` | VISA/serial backend not installed | §0 prerequisites |
| Only the load fails | wrong COM for Prologix, missing/`wrong GPIB:<n>`, mainframe GPIB addr mismatch | re-check §1/§2a |
| Load identifies as `NULL` | `load_slot` points to an empty slot | fix **Load slot** (§2b) |
| DAQ reads wrong tap / out of range | `daq_channel_map` wrong | fix the map (§2b) |
| `setlogic` does nothing / errors | `daq_relay_channel` unset or wrong | set it (§2b) |

---

## 5. First live run & known gaps

**First run:**
- [ ] Test Connection → all `[OK]`.
- [ ] Load the SPREOS `.tst`, select steps, enter Part Number + Serial Number.
- [ ] "Simulation mode" unchecked → **Start**.
- [ ] Watch the trace: instrument IDs appear at `getid` (INIT), then per-step results.
- [ ] **Safety:** Stop aborts the run; `disconnect()` drives **load input off** then
      **PS output off**. Keep the bench E-stop within reach for the first power-on.

**Known gaps / decisions to record during bring-up:**
1. **OVP/OCP** are not auto-programmed (§3 IDRC) — front-panel set, or add `set_protection` to `connect()`.
2. **Load power-band clamp** missing (§3 Prodigit) — add once datasheet boundaries known.
3. **`daq_relay_channel` is not validated by the preflight** — only the connection
   resources, `GPIB`, and `load_slot` are. Set it manually before any `setlogic` script;
   consider adding it to the preflight config check.
4. **One GPIB instrument per Prologix adapter** is assumed (only the load is on Prologix).
   If a second GPIB instrument ever shares that adapter, the driver must re-`++addr` per access.

---

*After this checklist passes on the real bench, capture the confirmed serial params,
VISA resources, `NAME?`/`*IDN?` strings, and any `protocol.py` tweaks back into the repo
(and the per-instrument READMEs) so the configuration is reproducible.*
