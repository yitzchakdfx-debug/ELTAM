"""PROVISIONAL command builders for the IDRC-040-076HR programmable DC PS.

!! TODO(manual): the exact command set, line termination, and whether the unit
echoes are NOT yet confirmed against the IDRC programming manual. The builders
below assume a conventional SCPI dialect. Keeping all framing here means
confirming the real protocol is a one-file change — the driver does not embed
any command strings.

Pure string builders — no I/O, unit-testable offline.
"""

from __future__ import annotations

IDN = "*IDN?"
RESET = "*RST"


def output(on: bool) -> str:
    return "OUTP ON" if on else "OUTP OFF"


def set_voltage(volts: float) -> str:
    return f"VOLT {float(volts):.3f}"


def measure_voltage() -> str:
    return "MEAS:VOLT?"


def measure_current() -> str:
    return "MEAS:CURR?"


def set_ovp(volts: float) -> str:
    return f"VOLT:PROT {float(volts):.3f}"


def set_ocp(amps: float) -> str:
    return f"CURR:PROT {float(amps):.3f}"
