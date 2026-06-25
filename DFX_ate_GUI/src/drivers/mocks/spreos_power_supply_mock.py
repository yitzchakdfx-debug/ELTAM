"""Stateful mock driver for `SPREOS Power Supply Main Card Fix.tst`.

This is a *test-specific* stand-in (not the generic
:class:`drivers.mock_hardware.MockHardware`). It models the instrument set
named in that script's INIT step and tracks the state set by side-effect
commands so that `readchannel` returns physically plausible values:

    CH1  IDRC-040-076HR  power-supply output (voltage AND idle current)
    CH3  DAQ-9600        JX1 voltage tap (tracks the PS input voltage)
    CH4  DAQ-9600        JX2-4 voltage tap (tracks the PS input voltage)
    CH5  3315G           electronic-load voltage AND current

Two channels (CH1, CH5) are read for two *different quantities* (volts and
amps) in this script. The channel number alone cannot tell them apart, so the
mock disambiguates using the active step's `Unit` (`V` vs `A`), supplied by the
runner through the optional :meth:`set_active_step` hook. If no context is set
(driver used without that hook), it falls back to a voltage reading.

The mock passes most of the time and fails occasionally: every measurement has
a `fail_prob` chance of being pushed just outside the step's limit window, so
runs realistically show the odd FAIL row without aborting (the script's
`Critical` steps carry no `Limits`, so they always pass).

When the real instruments arrive, replace this with a `BaseDriver` subclass
that talks to them — the channel map will change, as the V/A-on-one-channel
collision is an artifact of this mock-stage test program.
"""

from __future__ import annotations

import random
import time
from typing import ClassVar

from drivers.base_driver import BaseDriver, UnknownCommandError

# Unit strings (case-insensitive) that mean "this reading is a current".
_CURRENT_UNITS: frozenset[str] = frozenset({"a", "amp", "amps", "ampere", "amperes", "ma"})


class SpreosPowerSupplyMock(BaseDriver):
    """Simulates the SPREOS Power Supply Main Card test bench (Qt-free)."""

    MEASUREMENT_COMMANDS: ClassVar[frozenset[str]] = frozenset({"readchannel"})

    # Probability that any single measurement is nudged out of spec (FAIL).
    # Low by design: with ~20 measured steps in this script a default of 0.02
    # makes a *fully* passing run the common case (~0.98**20 ≈ 2 in 3) while
    # still throwing the occasional FAIL row. Raise it to fail more often.
    _DEFAULT_FAIL_PROB: ClassVar[float] = 0.02

    def __init__(self, *, fail_prob: float | None = None, seed: int | None = None) -> None:
        self.connected = False
        self._rng = random.Random(seed)
        self._fail_prob = (
            self._DEFAULT_FAIL_PROB if fail_prob is None else max(0.0, min(1.0, fail_prob))
        )

        # --- Simulated bench state (driven by side-effect commands) ---
        self._input_voltage: float = 0.0   # last `setvoltage`
        self._logic_on: bool = False       # last `setlogic on|off`
        self._load_watts: float = 0.0      # last `setload` (3315G constant power)

        # --- Active-step context (set by the runner via set_active_step) ---
        self._unit: str = ""
        self._min: float | None = None
        self._max: float | None = None

    # ------------------------------------------------------------------ #
    # BaseDriver lifecycle
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        time.sleep(0.2)
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    @property
    def measurement_commands(self) -> frozenset[str]:
        return self.MEASUREMENT_COMMANDS

    # ------------------------------------------------------------------ #
    # Optional context hook (duck-typed; see TestRunnerThread._run_step)
    # ------------------------------------------------------------------ #
    def set_active_step(
        self,
        unit: str = "",
        min_val: float | None = None,
        max_val: float | None = None,
    ) -> None:
        """Tell the mock the expected unit/limits of the step about to run.

        Used to (a) decide whether a reused channel is being read for volts or
        amps, and (b) know the limit window so an occasional reading can be
        nudged just outside it. Safe to call (or not) — defaults give a
        voltage reading with no forced failures keyed to a window.
        """
        self._unit = (unit or "").strip()
        self._min = min_val
        self._max = max_val

    # ------------------------------------------------------------------ #
    # Command dispatch
    # ------------------------------------------------------------------ #
    def execute_command(self, command: str, args: list[str]) -> float:
        cmd = command.lower()

        if cmd == "readchannel":
            channel = int(args[0]) if args else 0
            return self._read_channel(channel)

        if cmd == "setvoltage":
            self._input_voltage = float(args[0]) if args else 0.0
            time.sleep(0.05)
            return 0.0

        if cmd == "setlogic":
            # `setlogic on|off` — also tolerates `setlogic <line> on|off`.
            state = args[-1].lower() if args else "off"
            self._logic_on = state in ("on", "1", "true", "yes")
            time.sleep(0.05)
            return 0.0

        if cmd == "setload":
            # 3315G constant-power load, in watts.
            self._load_watts = float(args[0]) if args else 0.0
            time.sleep(0.05)
            return 0.0

        if cmd in ("getid", "relay"):
            time.sleep(0.05)
            return 0.0

        raise UnknownCommandError(f"Unknown hardware command: {command!r}")

    # ------------------------------------------------------------------ #
    # Measurement model
    # ------------------------------------------------------------------ #
    def _read_channel(self, channel: int) -> float:
        """Return a plausible reading for `channel`, given current bench state."""
        time.sleep(self._rng.uniform(0.1, 0.35))
        nominal = self._channel_nominal(channel)
        return self._sample(nominal)

    def _channel_nominal(self, channel: int) -> float:
        """Ideal value the bench *should* produce for the active reading."""
        wants_current = self._unit.lower() in _CURRENT_UNITS
        v = self._input_voltage

        if channel == 1:  # PS output: voltage, or idle current
            return self._ps_current() if wants_current else v
        if channel == 5:  # 3315G load: voltage, or constant-power current
            return self._load_current() if wants_current else v
        if channel in (2, 3, 4):  # DAQ voltage taps track the input rail
            return v
        return v  # unknown channel: behave like a voltage tap

    def _ps_current(self) -> float:
        """Power-supply output current (A). Small at idle; load-driven otherwise."""
        base = self._rng.uniform(0.12, 0.30)  # quiescent draw, no load
        if self._load_watts > 0 and self._logic_on and self._input_voltage > 0:
            base += self._load_watts / self._input_voltage
        return base

    def _load_current(self) -> float:
        """3315G constant-power current draw (A) = P / V when active."""
        if self._load_watts > 0 and self._logic_on and self._input_voltage > 0:
            return self._load_watts / self._input_voltage
        return self._rng.uniform(0.0, 0.05)  # negligible when load is off

    def _sample(self, nominal: float) -> float:
        """Add measurement jitter; occasionally push the reading out of spec."""
        if self._rng.random() < self._fail_prob:
            return self._out_of_window(nominal)

        # In-spec jitter: small enough to stay inside the typical limit windows
        # in this script (voltage ~±0.4 V, currents have ~±0.5 A+ margin).
        jitter = 0.06 + abs(nominal) * 0.01
        return round(nominal + self._rng.uniform(-jitter, jitter), 3)

    def _out_of_window(self, nominal: float) -> float:
        """A deliberately-failing reading, just outside the step's limits."""
        lo, hi = self._min, self._max
        if lo is not None and hi is not None:
            span = (hi - lo) or 1.0
            if self._rng.random() < 0.5:
                return round(lo - self._rng.uniform(0.05, 0.4) * span - 0.05, 3)
            return round(hi + self._rng.uniform(0.05, 0.4) * span + 0.05, 3)
        # No window known: just scatter widely around the nominal.
        return round(nominal + self._rng.uniform(-1.0, 1.0) + nominal * 0.4, 3)
