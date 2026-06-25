"""SCPI command builders for the GW Instek GPP-3610H DC power supply.

Commands CONFIRMED against the GW Instek GPP-series Programming Manual
(GPP-1000 Series Programming Manual, "Remote Interface" chapter):

    *IDN?                        identity
    :SOURce:VOLTage <v>          set output voltage   (manual example: "SOUR:VOLT 10")
    :SOURce:CURRent <a>          set output current limit
    :OUTPut[:STATe] {ON|OFF}     turn the output on/off
    :MEASure:VOLTage?            measured output voltage  -> volts
    :MEASure:CURRent?            measured output current  -> amps
    :MEASure:POWer?              measured output power    -> watts

The GPP-3610H is a SINGLE-output supply, so no channel prefix is needed
(multi-channel GPP models would prepend ":CHANnel<n>:").

Pure string building — no I/O, fully unit-testable offline.
"""

from __future__ import annotations

IDN = "*IDN?"
RESET = "*RST"
CLEAR_STATUS = "*CLS"
SYS_ERROR = ":SYSTem:ERRor?"

MEAS_VOLT = ":MEASure:VOLTage?"
MEAS_CURR = ":MEASure:CURRent?"
MEAS_POW = ":MEASure:POWer?"


def set_voltage(volts: float) -> str:
    return f":SOURce:VOLTage {float(volts):.4f}"


def set_current(amps: float) -> str:
    return f":SOURce:CURRent {float(amps):.4f}"


def output(on: bool) -> str:
    return f":OUTPut:STATe {'ON' if on else 'OFF'}"


def measure_voltage() -> str:
    return MEAS_VOLT


def measure_current() -> str:
    return MEAS_CURR


def measure_power() -> str:
    return MEAS_POW
