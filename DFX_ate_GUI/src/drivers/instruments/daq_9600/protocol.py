"""SCPI helpers for the GW Instek DAQ-9600 + DAQ-901 multiplexer.

Centralizes the SCPI strings so the driver reads cleanly and the command set is
documented in one place. Channel lists use the GW/Keysight `(@sccc)` form
(slot + channel), e.g. channel 101 -> "(@101)".

No I/O here — these are pure string builders (easy to unit-test without hardware).
"""

from __future__ import annotations

IDN = "*IDN?"
RESET = "*RST"
CLEAR_STATUS = "*CLS"
SYS_ERROR = "SYST:ERR?"

# Logical measurement function -> SCPI keyword.
_FUNCTIONS: dict[str, str] = {
    "DCV": "VOLT:DC",
    "ACV": "VOLT:AC",
    "DCI": "CURR:DC",
    "ACI": "CURR:AC",
    "RES": "RES",
    "FRES": "FRES",
    "TEMP": "TEMP",
    "FREQ": "FREQ",
}


def channel_list(channel: int) -> str:
    """Render one channel as a SCPI channel list, e.g. 101 -> '(@101)'."""
    return f"(@{int(channel)})"


def scpi_function(function: str) -> str:
    """Map a logical function name (e.g. 'DCV') to its SCPI keyword."""
    key = function.strip().upper()
    try:
        return _FUNCTIONS[key]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported DAQ-9600 function {function!r}; "
            f"known: {', '.join(sorted(_FUNCTIONS))}"
        ) from exc


def configure(channel: int, function: str) -> str:
    return f"CONF:{scpi_function(function)} {channel_list(channel)}"


def measure(channel: int, function: str) -> str:
    return f"MEAS:{scpi_function(function)}? {channel_list(channel)}"


def route_close(channel: int) -> str:
    return f"ROUT:CLOS {channel_list(channel)}"


def route_open(channel: int) -> str:
    return f"ROUT:OPEN {channel_list(channel)}"


def route_is_closed(channel: int) -> str:
    return f"ROUT:CLOS? {channel_list(channel)}"
