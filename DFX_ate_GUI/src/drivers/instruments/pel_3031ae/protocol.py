"""SCPI command builders for the GW Instek PEL-3031AE electronic load.

VERIFIED against the GW Instek / TEXIO PEL-3000(H) Series Programming Manual
(doc LSG_B71-0427, chapter 4 "Command" reference):

    *IDN?                               identity (e.g. "GW-INSTEK,PEL-3031AE,...")
    :MODE {CC|CR|CV|CP|CCCV|CRCV|CPCV}   set operating mode. The range is a
                                         SEPARATE command ([:MODE]:CRANge /
                                         [:MODE]:VRANge) — the mode itself is
                                         un-ranged (it is "CP", not "CPH").
    :POWer[:VA] <w>                      CP set level ("A value"), in watts
    :CURRent[:VA] <a>                    CC set level, in amps
    :VOLTage[:VA] <v>                    CV set level, in volts
    :RESistance[:VA] <r>                 CR set level, in ohms
    :INPut {ON|OFF}                      load input on/off  (NOT ":LOAD ...")
    :MEASure:VOLTage?                    measured terminal voltage -> volts
    :MEASure:CURRent?                    measured sink current     -> amps
    :MEASure:POWer?                      measured sink power       -> watts

The PEL-3000 addresses ONE load per unit — there is no channel-select command
(unlike the Prodigit mainframe, which needs "CHAN n").

Pure string building — no I/O, fully unit-testable offline.
"""

from __future__ import annotations

IDN = "*IDN?"
RESET = "*RST"
CLEAR_STATUS = "*CLS"
SYS_ERROR = ":SYSTem:ERRor?"

INPUT_ON = ":INPut ON"
INPUT_OFF = ":INPut OFF"
MEAS_VOLT = ":MEASure:VOLTage?"
MEAS_CURR = ":MEASure:CURRent?"
MEAS_POW = ":MEASure:POWer?"

# Operating modes accepted by ":MODE" (range is set separately; see module docstring).
_MODES = frozenset({"CC", "CR", "CV", "CP", "CCCV", "CRCV", "CPCV"})


def mode_token(mode: str) -> str:
    """Validate/normalize a load mode (e.g. 'cp' -> 'CP'); raise on unknown."""
    key = mode.strip().upper()
    if key not in _MODES:
        raise ValueError(
            f"Unsupported PEL load mode {mode!r}; known: {', '.join(sorted(_MODES))}"
        )
    return key


def set_mode(mode: str) -> str:
    return f":MODE {mode_token(mode)}"


def set_power(watts: float) -> str:
    return f":POWer {float(watts):.3f}"


def set_current(amps: float) -> str:
    return f":CURRent {float(amps):.4f}"


def set_voltage(volts: float) -> str:
    return f":VOLTage {float(volts):.4f}"


def set_input(on: bool) -> str:
    return INPUT_ON if on else INPUT_OFF


def measure_voltage() -> str:
    return MEAS_VOLT


def measure_current() -> str:
    return MEAS_CURR


def measure_power() -> str:
    return MEAS_POW
