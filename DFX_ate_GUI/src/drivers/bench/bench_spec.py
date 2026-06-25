"""Canonical definition of the SPREOS bench's instruments.

Single source of truth for the `instrument_connections` names each SPREOS
instrument is stored under (used by the factory to look up addresses and by the
Connections dialog to surface editable fields). Intentionally dependency-light —
no driver or Qt imports — so both layers can import it freely.
"""

from __future__ import annotations

# instrument_connections name keys (the Connections dialog edits these rows).
POWER_SUPPLY = "Power Supply"      # IDRC-040-076HR, serial
DAQ = "DAQ-9600"                   # GW Instek DAQ-9600, VISA
ELECTRONIC_LOAD = "Electronic Load"  # Prodigit 3300G/3315G via Prologix

#: Order shown in the Connections dialog.
BENCH_INSTRUMENT_NAMES: tuple[str, ...] = (POWER_SUPPLY, DAQ, ELECTRONIC_LOAD)
