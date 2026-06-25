"""Canonical definition of the SPREOS bench's instruments.

Single source of truth for the `instrument_connections` names each SPREOS
instrument is stored under (used by the factory to look up addresses and by the
Connections dialog to surface editable fields). Intentionally dependency-light —
no driver or Qt imports — so both layers can import it freely.
"""

from __future__ import annotations

# instrument_connections name keys (the Connections dialog edits these rows).
# Names are role-based and stable (stored in the DB); the model behind each role
# is the ELTAM bench hardware below. All three are addressed over VISA.
POWER_SUPPLY = "Power Supply"      # GW Instek GPP-3610H, VISA (USB-CDC/LAN/GPIB)
DAQ = "DAQ-9600"                   # GW Instek DAQ-9600 + DAQ-901 mux, VISA
ELECTRONIC_LOAD = "Electronic Load"  # GW Instek PEL-3031AE, VISA (USB-CDC/LAN/GPIB)

#: Order shown in the Connections dialog.
BENCH_INSTRUMENT_NAMES: tuple[str, ...] = (POWER_SUPPLY, DAQ, ELECTRONIC_LOAD)
