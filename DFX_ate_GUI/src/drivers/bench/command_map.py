"""Logical `.tst` channel -> instrument-role mapping for the bench router.

The `BenchDriver` routes `readchannel N` to one instrument *role* and picks the
quantity (volts vs amps) from the active step's `Unit`. This map is the
SPREOS-test default; it is product/test structure (not a hardware address), and
is expected to become a per-version, UI-editable map in a later phase.

Roles:
    SOURCE -> the programmable PS (IDRC)        — V or A by unit
    LOAD   -> the electronic load (Prodigit)    — V or A by unit
    DMM    -> a DAQ multiplexer voltage tap     — voltage read on channel N

NOTE: for DMM entries the BenchDriver forwards the *script* channel number to
`Multimeter.read()`. Mapping that logical number to the physical DAQ-901 mux
channel is deferred to the per-version channel map (a later phase); the mock
ignores the channel, so Simulation is unaffected.
"""

from __future__ import annotations

SOURCE = "source"
LOAD = "load"
DMM = "dmm"

# Unit strings (case-insensitive) that mean "this reading is a current".
CURRENT_UNITS: frozenset[str] = frozenset(
    {"a", "amp", "amps", "ampere", "amperes", "ma"}
)

# SPREOS Power Supply Main Card: CH1=PS, CH3/CH4=DAQ taps, CH5=load.
SPREOS_CHANNEL_MAP: dict[int, str] = {
    1: SOURCE,
    3: DMM,
    4: DMM,
    5: LOAD,
}


def wants_current(unit: str) -> bool:
    """True if a measurement unit denotes current (amps)."""
    return (unit or "").strip().lower() in CURRENT_UNITS
