"""Command builders for the Prodigit 3300G mainframe + 3315G electronic load.

Two layers are isolated here so the driver embeds no literals:

1. **Prologix GPIB-USB adapter control** (sent over the serial line; these start
   with `++`). `prologix_init(gpib)` puts the adapter in controller mode, targets
   the mainframe's single GPIB address, and enables auto read-after-write so a
   plain query gets its reply without an explicit `++read`.
2. **Prodigit SCPI, channel-routed.** The mainframe holds up to 4 load modules,
   so every operation first selects the slot (`CHAN n`) and then issues the
   command.

Return contract:
- Write-only operations return a `list[str]` of commands to send in order.
- Query operations return a `(pre_writes, query)` tuple: send the writes, then
  query the last string.

Pure string building — no I/O, fully unit-testable offline.

NOTE (3300G vs 3300F): the **G**-series sets constant power with `MODE CP` +
`POW <w>` (per the 3300G manual). The older 3300**F** family used
`CP:HIGH`/`CP:LOW`. This module targets the G.
"""

from __future__ import annotations

# --- Prologix GPIB-USB adapter control -------------------------------------
PROLOGIX_MODE_CONTROLLER = "++mode 1"
PROLOGIX_AUTO_ON = "++auto 1"


def prologix_set_address(gpib_address: int) -> str:
    return f"++addr {int(gpib_address)}"


def prologix_init(gpib_address: int) -> list[str]:
    """Adapter setup: controller mode, target GPIB address, auto read-after-write."""
    return [
        PROLOGIX_MODE_CONTROLLER,
        prologix_set_address(gpib_address),
        PROLOGIX_AUTO_ON,
    ]


# --- Prodigit SCPI ----------------------------------------------------------
NAME = "NAME?"          # identity / slot-presence probe ("NULL" = empty slot)
MEAS_VOLT = "MEAS:VOLT?"
MEAS_CURR = "MEAS:CURR?"
LOAD_ON = "LOAD ON"
LOAD_OFF = "LOAD OFF"

_MODES = frozenset({"CC", "CV", "CR", "CP"})


def select_channel(slot: int) -> str:
    return f"CHAN {int(slot)}"


def mode_token(mode: str) -> str:
    """Validate/normalize a load mode (e.g. 'cp' -> 'CP'); raise on unknown."""
    key = mode.strip().upper()
    if key not in _MODES:
        raise ValueError(
            f"Unsupported load mode {mode!r}; known: {', '.join(sorted(_MODES))}"
        )
    return key


def set_mode(slot: int, mode: str) -> list[str]:
    return [select_channel(slot), f"MODE {mode_token(mode)}"]


def set_power(slot: int, watts: float) -> list[str]:
    return [select_channel(slot), f"POW {float(watts):.3f}"]


def set_input(slot: int, on: bool) -> list[str]:
    return [select_channel(slot), LOAD_ON if on else LOAD_OFF]


def measure_voltage(slot: int) -> tuple[list[str], str]:
    return [select_channel(slot)], MEAS_VOLT


def measure_current(slot: int) -> tuple[list[str], str]:
    return [select_channel(slot)], MEAS_CURR


def identify(slot: int) -> tuple[list[str], str]:
    return [select_channel(slot)], NAME
